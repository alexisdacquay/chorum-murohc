export default function App() {
  return (
    <main className="reference-page">
      <header className="reference-header">
        <p className="reference-eyebrow">Foundation reference</p>
        <h1 className="reference-title">Chorum-murohc</h1>
        <p className="reference-intro">
          This visual-token reference demonstrates the neutral, accessible
          foundations used by future screens.
        </p>
      </header>

      <div className="reference-grid">
        <section
          aria-labelledby="colours-heading"
          className="token-section section-wide"
        >
          <div className="section-heading">
            <h2 id="colours-heading">Colours</h2>
            <p>Semantic roles keep meaning independent from a final brand.</p>
          </div>
          <ul className="colour-grid">
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-surface"
              />
              <span>surface</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-surface-muted"
              />
              <span>surface-muted</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-foreground"
              />
              <span>foreground</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-foreground-muted"
              />
              <span>foreground-muted</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-accent"
              />
              <span>accent</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-accent-hover"
              />
              <span>accent-hover</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-on-accent"
              />
              <span>on-accent</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-success"
              />
              <span>success</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-warning"
              />
              <span>warning</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-danger"
              />
              <span>danger</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-border"
              />
              <span>border</span>
            </li>
            <li className="colour-item">
              <span
                aria-hidden="true"
                className="colour-swatch bg-focus"
              />
              <span>focus</span>
            </li>
          </ul>
        </section>

        <section aria-labelledby="typography-heading" className="token-section">
          <div className="section-heading">
            <h2 id="typography-heading">Typography</h2>
            <p>A compact system scale keeps hierarchy predictable.</p>
          </div>
          <ul className="sample-list">
            <li>
              <span className="token-name">text-sm</span>
              <p className="text-sm">Small supporting text</p>
            </li>
            <li>
              <span className="token-name">text-body</span>
              <p className="text-body">Comfortable body copy</p>
            </li>
            <li>
              <span className="token-name">text-lead</span>
              <p className="text-lead font-medium">Inviting lead text</p>
            </li>
            <li>
              <span className="token-name">text-heading-2</span>
              <p className="text-heading-2 font-bold">Section heading</p>
            </li>
            <li>
              <span className="token-name">text-heading-1</span>
              <p className="text-heading-1 font-bold">Page heading</p>
            </li>
          </ul>
        </section>

        <section aria-labelledby="shape-heading" className="token-section">
          <div className="section-heading">
            <h2 id="shape-heading">Spacing and shape</h2>
            <p>One scale controls rhythm, corners, and elevation.</p>
          </div>
          <h3>Spacing</h3>
          <ul className="spacing-list">
            <li>
              <span className="token-name">spacing-1</span>
              <span aria-hidden="true" className="spacing-bar spacing-bar-1" />
            </li>
            <li>
              <span className="token-name">spacing-2</span>
              <span aria-hidden="true" className="spacing-bar spacing-bar-2" />
            </li>
            <li>
              <span className="token-name">spacing-3</span>
              <span aria-hidden="true" className="spacing-bar spacing-bar-3" />
            </li>
            <li>
              <span className="token-name">spacing-4</span>
              <span aria-hidden="true" className="spacing-bar spacing-bar-4" />
            </li>
            <li>
              <span className="token-name">spacing-6</span>
              <span aria-hidden="true" className="spacing-bar spacing-bar-6" />
            </li>
            <li>
              <span className="token-name">spacing-8</span>
              <span aria-hidden="true" className="spacing-bar spacing-bar-8" />
            </li>
            <li>
              <span className="token-name">spacing-12</span>
              <span
                aria-hidden="true"
                className="spacing-bar spacing-bar-12"
              />
            </li>
          </ul>
          <h3>Radii</h3>
          <ul className="shape-grid">
            <li className="shape-sample rounded-sm">
              <span>radius-sm</span>
            </li>
            <li className="shape-sample rounded-md">
              <span>radius-md</span>
            </li>
            <li className="shape-sample rounded-lg">
              <span>radius-lg</span>
            </li>
          </ul>
          <h3>Elevation</h3>
          <ul className="shape-grid">
            <li className="elevation-sample shadow-sm">
              <span>elevation-sm</span>
            </li>
            <li className="elevation-sample shadow-md">
              <span>elevation-md</span>
            </li>
          </ul>
        </section>

        <section aria-labelledby="states-heading" className="token-section">
          <div className="section-heading">
            <h2 id="states-heading">Interaction states</h2>
            <p>Native controls remain clear for touch and keyboard use.</p>
          </div>
          <div className="button-group">
            <button className="token-button token-button-primary" type="button">
              Primary action
            </button>
            <button className="token-button token-button-disabled" disabled type="button">
              Disabled action
            </button>
          </div>
          <div className="state-messages" aria-label="Status messages">
            <p className="state-message text-success">
              <strong>Success:</strong> The task is complete.
            </p>
            <p className="state-message text-warning">
              <strong>Warning:</strong> Check the details before continuing.
            </p>
            <p className="state-message text-danger">
              <strong>Danger:</strong> The action could not be completed.
            </p>
          </div>
        </section>

        <section aria-labelledby="motion-heading" className="token-section">
          <div className="section-heading">
            <h2 id="motion-heading">Motion</h2>
            <p>
              This demonstration is decorative and finite; its movement carries
              no information.
            </p>
          </div>
          <div className="motion-track" aria-hidden="true">
            <span className="motion-marker" />
          </div>
          <p className="motion-note">
            All meaning and state labels remain present when motion is reduced.
          </p>
        </section>
      </div>
    </main>
  )
}
