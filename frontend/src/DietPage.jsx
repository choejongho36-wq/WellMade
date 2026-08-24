import './MainPage.css'
import Sidebar, { useAuth } from './Sidebar.jsx'

const MEALS = [
  { time: '07:30', title: '아침', logged: false },
  { time: '12:40', title: '점심', logged: false },
  { time: '19:30', title: '저녁', logged: false },
]

function DietPage() {
  const { user } = useAuth()

  return (
    <div className="app revealed">
      <Sidebar />

      <main className="main">
        <div className="content">
          <div className="section-head">
            <div>
              <div className="section-eyebrow">MY WELLMADE</div>
              <div className="section-title">식단 관리</div>
            </div>
          </div>

          {user ? (
            <div className="diet-timeline">
              {MEALS.map((meal) => (
                <div className="diet-row" key={meal.time}>
                  <div className="diet-time">{meal.time}</div>
                  <div className="diet-line">
                    <div className={`diet-dot${meal.logged ? '' : ' pending'}`}></div>
                  </div>
                  <div className="diet-body">
                    {meal.logged ? (
                      <div className="diet-meal">
                        <div className="diet-meal-thumb"></div>
                        <div style={{ flex: 1 }}>
                          <div className="diet-meal-title">{meal.title}</div>
                          <div className="diet-meal-sub">{meal.desc}</div>
                        </div>
                        <div className="diet-meal-status">기록됨</div>
                      </div>
                    ) : (
                      <div className="diet-meal pending">
                        <div className="diet-meal-title">{meal.title} 식단 미기록</div>
                        <div className="diet-log-btn">+ 기록하기</div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="pcard-desc">로그인 후 식단을 기록할 수 있습니다.</p>
          )}
        </div>
      </main>
    </div>
  )
}

export default DietPage
