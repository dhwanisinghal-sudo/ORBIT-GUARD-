import { useState } from "react";
import { Link, useParams, Navigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { getLessonById, LESSONS } from "../data/lessons";
import "../styles/Learn.css";

function Quiz({ questions }) {
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);

  function select(qi, oi) {
    if (submitted) return;
    setAnswers((prev) => ({ ...prev, [qi]: oi }));
  }

  function submit(e) {
    e.preventDefault();
    setSubmitted(true);
  }

  function reset() {
    setAnswers({});
    setSubmitted(false);
  }

  const score = submitted
    ? questions.filter((q, i) => answers[i] === q.answer).length
    : 0;

  return (
    <div className="quiz-section">
      <h2>Knowledge Check</h2>
      <form onSubmit={submit}>
        {questions.map((q, qi) => (
          <div key={qi} className={`quiz-q${submitted ? " revealed" : ""}`}>
            <p className="quiz-question">
              {qi + 1}. {q.q}
            </p>
            <div className="quiz-options">
              {q.options.map((opt, oi) => {
                let cls = "quiz-opt";
                if (submitted) {
                  if (oi === q.answer) cls += " correct";
                  else if (answers[qi] === oi) cls += " wrong";
                } else if (answers[qi] === oi) {
                  cls += " selected";
                }
                return (
                  <button
                    type="button"
                    key={oi}
                    className={cls}
                    onClick={() => select(qi, oi)}
                  >
                    {opt}
                  </button>
                );
              })}
            </div>
            {submitted && (
              <div className="quiz-explanation">
                <strong>
                  {answers[qi] === q.answer ? "✓ Correct" : "✗ Incorrect"}
                </strong>{" "}
                — {q.explanation}
              </div>
            )}
          </div>
        ))}

        {!submitted ? (
          <button
            type="submit"
            className="quiz-submit"
            disabled={Object.keys(answers).length < questions.length}
          >
            Submit answers
          </button>
        ) : (
          <div className="quiz-results">
            <strong>
              Score: {score} / {questions.length}
            </strong>
            <button type="button" onClick={reset} className="quiz-reset">
              Try again
            </button>
          </div>
        )}
      </form>
    </div>
  );
}

export default function Lesson() {
  const { lessonId } = useParams();
  const lesson = getLessonById(lessonId);

  if (!lesson) return <Navigate to="/learn" replace />;

  const currentIdx = LESSONS.findIndex((l) => l.id === lessonId);
  const prev = currentIdx > 0 ? LESSONS[currentIdx - 1] : null;
  const next = currentIdx < LESSONS.length - 1 ? LESSONS[currentIdx + 1] : null;

  return (
    <div className="lesson-page page-content">
      <div className="lesson-breadcrumb">
        <Link to="/learn">Academy</Link>
        <span>›</span>
        <span>Module {lesson.module}</span>
      </div>

      <header className="lesson-header">
        <span className="lesson-emoji">{lesson.emoji}</span>
        <div className="lesson-eyebrow">MODULE {lesson.module}</div>
        <h1>{lesson.title}</h1>
        <p className="lesson-summary">{lesson.summary}</p>
      </header>

      <section className="lesson-objectives">
        <h2>Learning Objectives</h2>
        <ul>
          {lesson.objectives.map((obj, i) => (
            <li key={i}>{obj}</li>
          ))}
        </ul>
      </section>

      <div className="lesson-body">
        <ReactMarkdown>{lesson.content}</ReactMarkdown>
      </div>

      <section className="key-terms">
        <h2>Key Terms</h2>
        <dl className="terms-list">
          {lesson.keyTerms.map((t) => (
            <div key={t.term} className="term-item">
              <dt>{t.term}</dt>
              <dd>{t.def}</dd>
            </div>
          ))}
        </dl>
      </section>

      <Quiz questions={lesson.quiz} />

      <section className="lesson-resources">
        <h2>Verified Resources</h2>
        <ul className="resources-list">
          {lesson.resources.map((r, i) => (
            <li key={i}>
              <a href={r.url} target="_blank" rel="noopener noreferrer">
                {r.title} ↗
              </a>
            </li>
          ))}
        </ul>
      </section>

      <nav className="lesson-nav">
        {prev ? (
          <Link to={`/learn/${prev.id}`} className="lesson-nav-btn prev">
            ← {prev.title}
          </Link>
        ) : (
          <span />
        )}
        <Link to="/learn" className="lesson-nav-btn home">
          All modules
        </Link>
        {next ? (
          <Link to={`/learn/${next.id}`} className="lesson-nav-btn next">
            {next.title} →
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </div>
  );
}

