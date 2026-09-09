/**
 * The journey runtime.
 *
 * The driver page and the application share one origin, so the driver can
 * reach into the application's document exactly as a person reaches the
 * screen: it finds controls by their visible or accessible name, clicks
 * them, types into fields the way a keyboard does, and waits for what the
 * screen says next. It never calls the API directly and never reads
 * application state, so a journey can only pass if the interface really
 * works.
 *
 * Every report is scrubbed of the run's own passwords and PINs before it
 * leaves the browser, and the runner checks the scrubbing again on the way
 * out.
 */
;(function () {
  'use strict'

  var DEFAULT_TIMEOUT = 10000
  var POLL_INTERVAL = 50
  var SNAPSHOT_LIMIT = 700
  var REDACTED = '[redacted]'
  var MINIMUM_SECRET_LENGTH = 4

  var params = new URLSearchParams(location.search)
  var journeyName = params.get('journey') || 'smoke'
  var logElement = document.getElementById('log')
  var frame = document.getElementById('app')

  function log(line) {
    logElement.textContent += '\n' + line
  }

  function collectSecrets(node, found) {
    if (Array.isArray(node)) {
      node.forEach(function (value) {
        collectSecrets(value, found)
      })
      return found
    }
    if (node && typeof node === 'object') {
      Object.keys(node).forEach(function (key) {
        var value = node[key]
        if ((key === 'password' || key === 'pin') && typeof value === 'string') {
          found.push(value)
        } else {
          collectSecrets(value, found)
        }
      })
    }
    return found
  }

  function redact(text, secrets) {
    var maskable = secrets
      .filter(function (value) {
        return value.length >= MINIMUM_SECRET_LENGTH
      })
      .sort(function (a, b) {
        return b.length - a.length
      })
    return maskable.reduce(function (current, value) {
      return current.split(value).join(REDACTED)
    }, String(text))
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms)
    })
  }

  function accessibleName(element) {
    var label = element.getAttribute('aria-label')
    return (label === null ? element.textContent : label).trim()
  }

  function Runtime(dataset, secrets) {
    this.all = dataset
    this.dataset = dataset.journeys[journeyName]
    this.secrets = secrets
    this.steps = []
    // An audit journey reports what it found rather than asserting there is
    // nothing to find, so it collects here instead of throwing.
    this.findings = []
  }

  Runtime.prototype.doc = function () {
    return frame.contentDocument
  }

  Runtime.prototype.win = function () {
    return frame.contentWindow
  }

  Runtime.prototype.text = function () {
    var body = this.doc() && this.doc().body
    return body === null || body === undefined ? '' : body.innerText
  }

  Runtime.prototype.snapshot = function () {
    return redact(this.text(), this.secrets).slice(0, SNAPSHOT_LIMIT)
  }

  Runtime.prototype.record = function (label) {
    this.steps.push(label)
    log('ok   ' + label)
  }

  /** Wait until `probe` returns something truthy, or fail saying what was wanted. */
  Runtime.prototype.wait = async function (probe, label, timeout) {
    var deadline = Date.now() + (timeout || DEFAULT_TIMEOUT)
    var lastError = null
    while (Date.now() < deadline) {
      try {
        var found = probe()
        if (found) {
          return found
        }
      } catch (error) {
        lastError = error
      }
      await sleep(POLL_INTERVAL)
    }
    throw new Error(
      'timed out waiting for ' +
        label +
        (lastError === null ? '' : ' (last error: ' + lastError.message + ')'),
    )
  }

  Runtime.prototype.expect = function (condition, label) {
    if (!condition) {
      throw new Error('expected ' + label)
    }
    this.record(label)
  }

  Runtime.prototype.waitForText = async function (needle, label) {
    var runtime = this
    await this.wait(
      function () {
        return runtime.text().indexOf(needle) !== -1
      },
      label || 'the screen to say "' + needle + '"',
    )
    this.record(label || 'screen says "' + needle + '"')
  }

  Runtime.prototype.expectNoText = function (needle, label) {
    this.expect(this.text().indexOf(needle) === -1, label)
  }

  /** Every control a person could activate, inside `root` or the whole page. */
  Runtime.prototype.controls = function (root) {
    var scope = root || this.doc()
    return Array.prototype.slice.call(
      scope.querySelectorAll('button, a[href], input[type="radio"]'),
    )
  }

  Runtime.prototype.findControl = function (name, root) {
    return (
      this.controls(root).filter(function (element) {
        return accessibleName(element) === name && !element.disabled
      })[0] || null
    )
  }

  Runtime.prototype.control = async function (name, root) {
    var runtime = this
    return this.wait(
      function () {
        return runtime.findControl(name, root)
      },
      'an enabled control named "' + name + '"',
    )
  }

  Runtime.prototype.click = async function (name, root) {
    var element = await this.control(name, root)
    element.click()
    this.record('clicked "' + name + '"')
    return element
  }

  /** The one open dialog, once it is there. */
  Runtime.prototype.dialog = async function (titleFragment) {
    var runtime = this
    return this.wait(
      function () {
        var open = runtime.doc().querySelector('[role="dialog"]')
        if (open === null) {
          return null
        }
        if (titleFragment && open.innerText.indexOf(titleFragment) === -1) {
          return null
        }
        return open
      },
      'a dialog' + (titleFragment ? ' about "' + titleFragment + '"' : ''),
    )
  }

  Runtime.prototype.noDialog = async function (label) {
    var runtime = this
    await this.wait(
      function () {
        return runtime.doc().querySelector('[role="dialog"]') === null
      },
      label || 'the dialog to close',
    )
    this.record(label || 'dialog closed')
  }

  /** The field a visible label points at. */
  Runtime.prototype.field = async function (labelText, root) {
    var runtime = this
    return this.wait(
      function () {
        var scope = root || runtime.doc()
        var labels = Array.prototype.slice.call(scope.querySelectorAll('label'))
        var match = labels.filter(function (label) {
          return label.textContent.trim() === labelText
        })[0]
        if (match === undefined) {
          return null
        }
        var field = runtime.doc().getElementById(match.htmlFor)
        return field === null || field.disabled ? null : field
      },
      'a field labelled "' + labelText + '"',
    )
  }

  /**
   * Type into a controlled React field.
   *
   * Assigning `.value` alone is invisible to React, which tracks the last
   * value it wrote. The native setter plus a bubbling `input` event is what
   * a real keystroke produces.
   */
  Runtime.prototype.fill = async function (labelText, value, root) {
    var field = await this.field(labelText, root)
    var win = this.win()
    var prototype =
      field.tagName === 'TEXTAREA'
        ? win.HTMLTextAreaElement.prototype
        : win.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(field, value)
    field.dispatchEvent(new win.Event('input', { bubbles: true }))
    this.record('filled "' + labelText + '"')
    return field
  }

  /** Pick a radio option by the text of the label that wraps it. */
  Runtime.prototype.choose = async function (optionText) {
    var runtime = this
    var input = await this.wait(
      function () {
        var labels = Array.prototype.slice.call(
          runtime.doc().querySelectorAll('label'),
        )
        var match = labels.filter(function (label) {
          return label.textContent.indexOf(optionText) !== -1
        })[0]
        if (match === undefined) {
          return null
        }
        var radio = match.querySelector('input[type="radio"]')
        return radio === null || radio.disabled ? null : radio
      },
      'a selectable option containing "' + optionText + '"',
    )
    input.click()
    this.record('chose an option')
    return input
  }

  /** The text of the one element carrying a test identifier. */
  Runtime.prototype.readTestId = async function (testId) {
    var runtime = this
    var element = await this.wait(
      function () {
        return runtime.doc().querySelector('[data-testid="' + testId + '"]')
      },
      'the element marked "' + testId + '"',
    )
    return element.textContent.trim()
  }

  Runtime.prototype.load = async function (path) {
    var runtime = this
    var settled = false
    frame.addEventListener(
      'load',
      function () {
        settled = true
      },
      { once: true },
    )
    frame.src = path
    await this.wait(
      function () {
        return settled
      },
      'the application to load ' + path,
    )
    await this.wait(
      function () {
        return runtime.text().length > 0
      },
      'the application to render',
    )
    this.record('loaded ' + path)
  }

  Runtime.prototype.signIn = async function (credentials, landingText) {
    await this.fill('Username', credentials.username)
    await this.fill('Password', credentials.password)
    await this.click('Sign in')
    await this.waitForText(landingText, 'signed in and landed on "' + landingText + '"')
  }

  Runtime.prototype.signOut = async function () {
    await this.click('Sign out')
    await this.waitForText('Sign in', 'signed out')
  }

  Runtime.prototype.goTo = async function (navLabel, headingText) {
    await this.click(navLabel)
    await this.waitForText(headingText || navLabel, 'opened ' + navLabel)
  }

  async function run() {
    var datasetResponse = await fetch('/__harness__/dataset')
    var dataset = await datasetResponse.json()
    var secrets = collectSecrets(dataset, [])
    var runtime = new Runtime(dataset, secrets)
    var started = Date.now()
    var report = { journey: journeyName, run: dataset.token, ok: false }

    try {
      var journey = window.CHORUM_JOURNEYS[journeyName]
      if (typeof journey !== 'function') {
        throw new Error('no journey named "' + journeyName + '"')
      }
      await runtime.load('/')
      await journey(runtime)
      report.ok = true
    } catch (error) {
      report.ok = false
      report.failure = redact(String(error && error.message ? error.message : error), secrets)
      report.screen = runtime.snapshot()
      log('FAIL ' + report.failure)
    }

    if (runtime.findings.length > 0) {
      report.findings = runtime.findings.map(function (finding) {
        return {
          screen: finding.screen,
          rule: finding.rule,
          detail: redact(String(finding.detail), secrets),
        }
      })
    }
    report.steps = runtime.steps.map(function (step) {
      return redact(step, secrets)
    })
    report.elapsedMs = Date.now() - started
    await fetch('/__harness__/report?journey=' + encodeURIComponent(journeyName), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(report),
    })
    log(report.ok ? 'PASSED' : 'FAILED')
  }

  window.CHORUM_JOURNEYS = {}
  var script = document.createElement('script')
  script.src = '/__harness__/journeys/' + encodeURIComponent(journeyName) + '.js'
  script.onload = function () {
    run().catch(function (error) {
      log('driver crashed: ' + error)
    })
  }
  script.onerror = function () {
    log('could not load the journey script')
  }
  document.head.appendChild(script)
})()
