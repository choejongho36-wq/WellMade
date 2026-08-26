import { Component } from 'react'
import { Link } from 'react-router-dom'
import './ErrorBoundary.css'
import PageShell from './PageShell.jsx'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error('Unhandled render error', error, info)
  }

  render() {
    if (!this.state.hasError) return this.props.children

    return (
      <PageShell>
        <div className="error-split">
          <div className="error-left">
            <div className="page-index-tag">ERROR</div>
            <h1 className="error-title">문제가 발생했어요.</h1>
            <p className="error-sub">
              예상치 못한 오류가 발생했어요. 새로고침해도 안 되면 홈으로 돌아가주세요.
            </p>
            <div className="error-actions">
              <button className="error-cta" onClick={() => window.location.reload()}>
                새로고침
              </button>
              <Link to="/" className="error-cta error-cta-secondary">
                홈으로 돌아가기
              </Link>
            </div>
          </div>
          <div className="error-right">
            <div className="error-band"></div>
            <div className="error-mark">!</div>
            <div className="error-index">SOMETHING WRONG</div>
          </div>
        </div>
      </PageShell>
    )
  }
}

export default ErrorBoundary
