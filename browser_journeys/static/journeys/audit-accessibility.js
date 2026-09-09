/**
 * The current-scope accessibility audit (T094).
 *
 * It walks every built screen in a real browser and runs one bounded set of
 * deterministic WCAG 2.2 AA checks over each: text alternatives, accessible
 * names, heading structure, identifier integrity, dangling ARIA references,
 * focus visibility, pointer target size and text contrast. It then does one
 * representative keyboard pass over a dialog, which is where keyboard
 * handling actually breaks.
 *
 * The checks are written here rather than pulled from a library because the
 * repository is deliberately dependency-light and every rule below is a few
 * lines of DOM work. What that buys is no new dependency; what it costs is
 * the breadth a full engine would have, which is recorded in the audit
 * write-up rather than hidden.
 *
 * This journey never fails on a finding. It reports what it found; fixing is
 * a separate backlog entry, per T094.
 */
window.CHORUM_JOURNEYS['audit-accessibility'] = async function (t) {
  var LARGE_TEXT_PX = 24
  var LARGE_BOLD_PX = 18.66
  var MINIMUM_TARGET = 24
  var CONTRAST_NORMAL = 4.5
  var CONTRAST_LARGE = 3

  var seen = {}

  function note(screen, rule, detail) {
    var key = screen + '|' + rule + '|' + detail
    if (seen[key] === undefined) {
      seen[key] = true
      t.findings.push({ screen: screen, rule: rule, detail: detail })
    }
  }

  function win() {
    return t.win()
  }

  function doc() {
    return t.doc()
  }

  function all(selector) {
    return Array.prototype.slice.call(doc().querySelectorAll(selector))
  }

  function visible(element) {
    var style = win().getComputedStyle(element)
    if (style.visibility === 'hidden' || style.display === 'none') {
      return false
    }
    var box = element.getBoundingClientRect()
    return box.width > 0 || box.height > 0
  }

  function describe(element) {
    var name = element.tagName.toLowerCase()
    if (element.id) {
      name += '#' + element.id
    }
    var text = (element.textContent || '').trim().slice(0, 40)
    return text === '' ? name : name + ' "' + text + '"'
  }

  function accessibleName(element) {
    var label = element.getAttribute('aria-label')
    if (label !== null && label.trim() !== '') {
      return label.trim()
    }
    var labelledBy = element.getAttribute('aria-labelledby')
    if (labelledBy !== null) {
      var joined = labelledBy
        .split(/\s+/)
        .map(function (id) {
          var target = doc().getElementById(id)
          return target === null ? '' : target.textContent
        })
        .join(' ')
        .trim()
      if (joined !== '') {
        return joined
      }
    }
    if (element.id !== '') {
      var explicit = all('label').filter(function (candidate) {
        return candidate.htmlFor === element.id
      })[0]
      if (explicit !== undefined) {
        return explicit.textContent.trim()
      }
    }
    var wrapping = element.closest('label')
    if (wrapping !== null) {
      return wrapping.textContent.trim()
    }
    if (element.tagName === 'INPUT' && element.value !== '') {
      return String(element.value).trim()
    }
    var title = element.getAttribute('title')
    if (title !== null && title.trim() !== '') {
      return title.trim()
    }
    return (element.textContent || '').trim()
  }

  function parseColour(value) {
    var match = /rgba?\(([^)]+)\)/.exec(value)
    if (match === null) {
      return null
    }
    var parts = match[1]
      .split(/[\s,\/]+/)
      .filter(function (piece) {
        return piece !== ''
      })
      .map(Number)
    return {
      r: parts[0],
      g: parts[1],
      b: parts[2],
      a: parts.length > 3 ? parts[3] : 1,
    }
  }

  function channel(value) {
    var scaled = value / 255
    return scaled <= 0.03928
      ? scaled / 12.92
      : Math.pow((scaled + 0.055) / 1.055, 2.4)
  }

  function luminance(colour) {
    return (
      0.2126 * channel(colour.r) +
      0.7152 * channel(colour.g) +
      0.0722 * channel(colour.b)
    )
  }

  function contrast(foreground, background) {
    var first = luminance(foreground) + 0.05
    var second = luminance(background) + 0.05
    return first > second ? first / second : second / first
  }

  function over(top, bottom) {
    return {
      r: top.r * top.a + bottom.r * (1 - top.a),
      g: top.g * top.a + bottom.g * (1 - top.a),
      b: top.b * top.a + bottom.b * (1 - top.a),
      a: 1,
    }
  }

  function backgroundBehind(element) {
    var stack = []
    var node = element
    while (node !== null) {
      var colour = parseColour(win().getComputedStyle(node).backgroundColor)
      if (colour !== null && colour.a > 0) {
        stack.push(colour)
        if (colour.a === 1) {
          break
        }
      }
      node = node.parentElement
    }
    var base = { r: 255, g: 255, b: 255, a: 1 }
    for (var index = stack.length - 1; index >= 0; index -= 1) {
      base = over(stack[index], base)
    }
    return base
  }

  function ownText(element) {
    return Array.prototype.slice
      .call(element.childNodes)
      .filter(function (node) {
        return node.nodeType === 3
      })
      .map(function (node) {
        return node.textContent
      })
      .join('')
      .trim()
  }

  function checkTextAlternatives(screen) {
    all('img').forEach(function (image) {
      if (!image.hasAttribute('alt')) {
        note(
          screen,
          '1.1.1 non-text content',
          'image with no alt attribute: ' + (image.getAttribute('src') || '?'),
        )
      }
    })
  }

  function checkNames(screen) {
    all('button, a[href], select, textarea, input, [role="button"]').forEach(
      function (element) {
        if (element.type === 'hidden' || !visible(element)) {
          return
        }
        examined.controls += 1
        if (accessibleName(element) === '') {
          note(
            screen,
            '4.1.2 name, role, value',
            'control with no accessible name: ' + describe(element),
          )
        }
      },
    )
  }

  function checkIdentifiers(screen) {
    var counts = {}
    all('[id]').forEach(function (element) {
      counts[element.id] = (counts[element.id] || 0) + 1
    })
    Object.keys(counts).forEach(function (id) {
      if (counts[id] > 1) {
        note(screen, '4.1.1 parsing', 'duplicate id used ' + counts[id] + ' times')
      }
    })
    ;['aria-labelledby', 'aria-describedby', 'aria-controls'].forEach(
      function (attribute) {
        all('[' + attribute + ']').forEach(function (element) {
          element
            .getAttribute(attribute)
            .split(/\s+/)
            .forEach(function (id) {
              if (id !== '' && doc().getElementById(id) === null) {
                note(
                  screen,
                  '4.1.2 name, role, value',
                  attribute + ' points at a missing id on ' + describe(element),
                )
              }
            })
        })
      },
    )
    all('[tabindex]').forEach(function (element) {
      if (Number(element.getAttribute('tabindex')) > 0) {
        note(
          screen,
          '2.4.3 focus order',
          'positive tabindex on ' + describe(element),
        )
      }
    })
  }

  function checkHeadings(screen) {
    var headings = all('h1, h2, h3, h4, h5, h6').filter(visible)
    var levels = headings.map(function (heading) {
      return Number(heading.tagName.slice(1))
    })
    if (levels.indexOf(1) === -1) {
      note(screen, '1.3.1 info and relationships', 'no level-1 heading')
    }
    for (var index = 1; index < levels.length; index += 1) {
      if (levels[index] - levels[index - 1] > 1) {
        note(
          screen,
          '1.3.1 info and relationships',
          'heading level jumps from h' +
            levels[index - 1] +
            ' to h' +
            levels[index],
        )
      }
    }
  }

  function checkLandmarks(screen) {
    if (doc().querySelector('main') === null) {
      note(screen, '1.3.6 landmarks', 'no main landmark')
    }
    if (doc().querySelector('h1') === null) {
      return
    }
  }

  function checkTargetSize(screen) {
    all('button, a[href], input[type="radio"], input[type="checkbox"]').forEach(
      function (element) {
        if (!visible(element)) {
          return
        }
        // 2.5.8 exempts a link sitting inside a sentence of text.
        if (element.tagName === 'A' && element.closest('p') !== null) {
          return
        }
        var box = element.getBoundingClientRect()
        if (box.width < MINIMUM_TARGET || box.height < MINIMUM_TARGET) {
          note(
            screen,
            '2.5.8 target size (minimum)',
            describe(element) +
              ' is ' +
              Math.round(box.width) +
              'x' +
              Math.round(box.height) +
              ' css px',
          )
        }
      },
    )
  }

  function checkFocusVisible(screen) {
    all('button, a[href], input, select, textarea').forEach(function (element) {
      if (element.type === 'hidden' || !visible(element) || element.disabled) {
        return
      }
      element.focus()
      if (doc().activeElement !== element) {
        return
      }
      var style = win().getComputedStyle(element)
      var hasOutline = style.outlineStyle !== 'none' && style.outlineWidth !== '0px'
      if (!hasOutline && style.boxShadow === 'none') {
        note(
          screen,
          '2.4.7 focus visible',
          'no focus indicator on ' + describe(element),
        )
      }
    })
    if (doc().activeElement !== null) {
      doc().activeElement.blur()
    }
  }

  var examined = { text: 0, controls: 0 }

  function checkContrast(screen) {
    all('body *').forEach(function (element) {
      if (!visible(element) || ownText(element) === '') {
        return
      }
      examined.text += 1
      var style = win().getComputedStyle(element)
      var foreground = parseColour(style.color)
      if (foreground === null) {
        return
      }
      var background = backgroundBehind(element)
      var blended = foreground.a < 1 ? over(foreground, background) : foreground
      var size = parseFloat(style.fontSize)
      var bold = Number(style.fontWeight) >= 700
      var large = size >= LARGE_TEXT_PX || (bold && size >= LARGE_BOLD_PX)
      var required = large ? CONTRAST_LARGE : CONTRAST_NORMAL
      var measured = contrast(blended, background)
      if (measured + 0.005 < required) {
        note(
          screen,
          '1.4.3 contrast (minimum)',
          describe(element) +
            ' measures ' +
            measured.toFixed(2) +
            ':1, needs ' +
            required +
            ':1',
        )
      }
    })
  }

  function checkDocument(screen) {
    var root = doc().documentElement
    if (!root.hasAttribute('lang') || root.getAttribute('lang').trim() === '') {
      note(screen, '3.1.1 language of page', 'the html element has no lang')
    }
    if (doc().title.trim() === '') {
      note(screen, '2.4.2 page titled', 'the document has no title')
    }
  }

  function auditScreen(screen) {
    examined.text = 0
    examined.controls = 0
    checkDocument(screen)
    checkTextAlternatives(screen)
    checkNames(screen)
    checkIdentifiers(screen)
    checkHeadings(screen)
    checkLandmarks(screen)
    checkTargetSize(screen)
    checkContrast(screen)
    checkFocusVisible(screen)
    t.record(
      'audited ' +
        screen +
        ': ' +
        examined.controls +
        ' control(s), ' +
        examined.text +
        ' text element(s)',
    )
  }

  // The signed-out screen first, because it is the only one a stranger sees.
  await t.waitForText('Sign in', 'the sign-in screen is reachable')
  auditScreen('sign-in')

  await t.signIn(t.dataset.child, 'Chores')

  // Bookmarking and reloading a screen is how people move around a site.
  // Check where a direct request for one actually lands.
  await t.load('/points')
  if (t.win().location.pathname !== '/points') {
    note(
      'navigation',
      '2.4.5 multiple ways',
      'loading /points directly landed on ' +
        t.win().location.pathname +
        ', so a bookmark or a reload loses the screen',
    )
  } else {
    t.record('a direct request for /points stays on /points')
  }

  var childScreens = [
    ['Chores', 'Chores'],
    ['Points', 'Your balance'],
    ['Rewards', 'Rewards'],
    ['Levels', 'Levels'],
    ['Creature', 'Creature'],
  ]
  for (var childIndex = 0; childIndex < childScreens.length; childIndex += 1) {
    var childRoute = childScreens[childIndex]
    await t.goTo(childRoute[0], childRoute[1])
    auditScreen('child ' + childRoute[0].toLowerCase())
  }

  // One representative keyboard pass, on the interaction most likely to trap
  // a keyboard user: a modal dialog.
  await t.goTo('Chores')
  var trigger = await t.control('Mark Sweep the hall as done')
  trigger.focus()
  trigger.click()
  var dialog = await t.dialog('Mark "Sweep the hall" as done?')
  await t.wait(
    function () {
      return dialog.contains(t.doc().activeElement)
    },
    'focus to move into the dialog',
  )
  t.record('keyboard: focus moves into the dialog when it opens')
  dialog.dispatchEvent(
    new (t.win().KeyboardEvent)('keydown', {
      key: 'Escape',
      bubbles: true,
    }),
  )
  await t.noDialog('keyboard: Escape closes the dialog')
  // Radix restores focus to the trigger, but only if the dialog is still
  // mounted when it closes. Report where focus actually landed.
  var landed = await t.wait(
    function () {
      return t.doc().activeElement
    },
    'focus to settle after the dialog closes',
  )
  if (landed === trigger) {
    t.record('keyboard: focus returns to the control that opened the dialog')
  } else {
    note(
      'child chores',
      '2.4.3 focus order',
      'after a dialog closes with Escape, focus goes to ' +
        describe(landed) +
        ' rather than back to the control that opened it',
    )
  }

  await t.signOut()
  await t.load('/')
  await t.signIn(t.dataset.parent, 'Overview')
  var parentScreens = [
    ['Overview', 'Overview'],
    ['Approvals', 'Approvals'],
    ['Chore pool', 'Chore pool'],
    ['Reward requests', 'Reward requests'],
    ['Household', 'Household'],
    ['Activity', 'Activity'],
    ['Approval PIN', 'Approval PIN'],
  ]
  for (var parentIndex = 0; parentIndex < parentScreens.length; parentIndex += 1) {
    var parentRoute = parentScreens[parentIndex]
    await t.goTo(parentRoute[0], parentRoute[1])
    auditScreen('parent ' + parentRoute[0].toLowerCase())
  }

  t.record('audited every built screen; ' + t.findings.length + ' finding(s)')
}
