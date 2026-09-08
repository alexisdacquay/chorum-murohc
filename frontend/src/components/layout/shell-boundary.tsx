import {
  Component,
  createRef,
  type ErrorInfo,
  type ReactNode,
} from 'react'

import { Button } from '../ui/button'

interface ShellBoundaryProps {
  children: ReactNode
  contentKey: string
  onRecover: () => void
}

interface ShellBoundaryState {
  contentKey: string
  hasError: boolean
  retryAttempt: number
}

export class ShellBoundary extends Component<
  ShellBoundaryProps,
  ShellBoundaryState
> {
  state: ShellBoundaryState = {
    contentKey: this.props.contentKey,
    hasError: false,
    retryAttempt: 0,
  }

  private readonly alertRef = createRef<HTMLDivElement>()
  private focusTimer: ReturnType<typeof setTimeout> | undefined

  static getDerivedStateFromProps(
    props: ShellBoundaryProps,
    state: ShellBoundaryState,
  ): Partial<ShellBoundaryState> | null {
    if (props.contentKey !== state.contentKey) {
      return {
        contentKey: props.contentKey,
        hasError: false,
      }
    }

    return null
  }

  static getDerivedStateFromError(): Partial<ShellBoundaryState> {
    return { hasError: true }
  }

  componentDidCatch(_error: unknown, _info: ErrorInfo) {
    // React owns developer diagnostics; the user-facing fallback stays generic.
  }

  componentDidMount() {
    if (this.state.hasError) {
      this.focusAlert()
    }
  }

  componentDidUpdate(
    _previousProps: ShellBoundaryProps,
    previousState: ShellBoundaryState,
  ) {
    const retryFinished =
      previousState.retryAttempt !== this.state.retryAttempt

    if (
      this.state.hasError &&
      (!previousState.hasError || retryFinished)
    ) {
      this.focusAlert()
    } else if (!this.state.hasError && retryFinished) {
      this.props.onRecover()
    }
  }

  componentWillUnmount() {
    if (this.focusTimer !== undefined) {
      clearTimeout(this.focusTimer)
    }
  }

  private focusAlert() {
    if (this.focusTimer !== undefined) {
      clearTimeout(this.focusTimer)
    }

    this.focusTimer = setTimeout(() => {
      this.alertRef.current?.focus()
      this.focusTimer = undefined
    }, 0)
  }

  private readonly retry = () => {
    this.setState((state) => ({
      hasError: false,
      retryAttempt: state.retryAttempt + 1,
    }))
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          aria-labelledby="shell-error-title"
          className="shell-feedback shell-error"
          ref={this.alertRef}
          role="alert"
          tabIndex={-1}
        >
          <h2 id="shell-error-title">Something went wrong</h2>
          <p>We could not show this page. Try again.</p>
          <Button onClick={this.retry}>Try again</Button>
        </div>
      )
    }

    return this.props.children
  }
}
