import { useEffect, useState } from 'react'
import PageShell from '../components/PageShell.jsx'
import { useAuth } from '../lib/auth.js'
import './SupportPages.css'

export default function FaqPage() {
  const { getFaqs } = useAuth()
  const [faqs, setFaqs] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getFaqs().then(setFaqs).catch((err) => setError(err.message))
  }, [getFaqs])

  return (
    <PageShell>
      <div className="support-page">
        <p className="support-eyebrow">FAQ</p>
        <h1 className="support-title">자주 묻는 질문</h1>
        <p className="support-hint">궁금한 점을 먼저 확인해보세요.</p>

        {error && <p className="support-error">{error}</p>}

        {faqs && faqs.length === 0 && <p className="support-empty">등록된 FAQ가 없습니다.</p>}

        {faqs && faqs.length > 0 && (
          <div className="support-faq-list">
            {faqs.map((faq) => (
              <details className="support-faq-item" key={faq.id}>
                <summary>{faq.question}</summary>
                <p>{faq.answer}</p>
              </details>
            ))}
          </div>
        )}
      </div>
    </PageShell>
  )
}
