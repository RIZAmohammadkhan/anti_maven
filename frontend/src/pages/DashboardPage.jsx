import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getHistory, deleteHistoryItem, initPersonalization, submitPersonalizationAnswers, createResearchStream } from '../api/client';
import Navbar from '../components/Navbar';
import SearchHistory from '../components/SearchHistory';
import PersonalizationModal from '../components/PersonalizationModal';
import LoadingTerminal from '../components/LoadingTerminal';
import ResultsView from '../components/ResultsView';
import ProductDrawer from '../components/ProductDrawer';

// App phases
const PHASE = {
  SEARCH: 'search',
  PERSONALIZE: 'personalize',
  LOADING: 'loading',
  RESULTS: 'results',
};

export default function DashboardPage() {
  const { user } = useAuth();
  const [phase, setPhase] = useState(PHASE.SEARCH);
  const [query, setQuery] = useState('');
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  // Personalization
  const [sessionId, setSessionId] = useState(null);
  const [questions, setQuestions] = useState([]);

  // Loading & results
  const [logs, setLogs] = useState([]);
  const [results, setResults] = useState(null);
  const [products, setProducts] = useState([]);
  const [drawerProduct, setDrawerProduct] = useState(null);

  const eventSourceRef = useRef(null);
  const timerRef = useRef(null);
  const [elapsed, setElapsed] = useState(0);

  // Fetch history on mount
  useEffect(() => {
    loadHistory();
  }, []);

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const data = await getHistory();
      setHistory(data);
    } catch {
      // silently fail
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleDeleteHistory(id) {
    try {
      await deleteHistoryItem(id);
      setHistory((h) => h.filter((item) => item.id !== id));
    } catch {
      // ignore
    }
  }

  function handleViewHistory(item) {
    setResults({ products: item.products || [], final_recommendation: item.recommendation || '' });
    setProducts(item.products || []);
    setPhase(PHASE.RESULTS);
  }

  // Search flow
  async function handleSearch(e) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    try {
      const data = await initPersonalization(q);
      setSessionId(data.session_id);
      setQuestions(data.questions || []);
      if (data.questions && data.questions.length > 0) {
        setPhase(PHASE.PERSONALIZE);
      } else {
        startStream({ sessionId: data.session_id });
      }
    } catch {
      startStream({ query: q });
    }
  }

  function handleSkipPersonalization() {
    startStream({ sessionId });
  }

  async function handleSubmitPersonalization(answers) {
    try {
      await submitPersonalizationAnswers(sessionId, answers);
    } catch {
      // proceed anyway
    }
    startStream({ sessionId });
  }

  // Stream
  function startStream({ query: q, sessionId: sid }) {
    setPhase(PHASE.LOADING);
    setLogs([]);
    setElapsed(0);

    const startTime = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Date.now() - startTime);
    }, 100);

    if (eventSourceRef.current) eventSourceRef.current.close();

    const es = createResearchStream({
      query: q || undefined,
      sessionId: sid || undefined,
      userId: user?.id,
    });
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'progress') {
        setLogs((prev) => [...prev, { text: data.message, time: new Date() }]);
      } else if (data.type === 'complete') {
        clearInterval(timerRef.current);
        setResults(data.data);
        setProducts(data.data.products || []);
        setPhase(PHASE.RESULTS);
        es.close();
        loadHistory(); // refresh history
      } else if (data.type === 'error') {
        clearInterval(timerRef.current);
        alert('Error: ' + data.message);
        resetToSearch();
        es.close();
      }
    };

    es.onerror = () => {
      clearInterval(timerRef.current);
      es.close();
    };
  }

  function resetToSearch() {
    if (eventSourceRef.current) eventSourceRef.current.close();
    clearInterval(timerRef.current);
    setPhase(PHASE.SEARCH);
    setQuery('');
    setSessionId(null);
    setQuestions([]);
    setLogs([]);
    setResults(null);
    setProducts([]);
    setDrawerProduct(null);
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) eventSourceRef.current.close();
      clearInterval(timerRef.current);
    };
  }, []);

  return (
    <div className="min-h-screen flex flex-col font-sans relative bg-beige-50">
      <Navbar />

      <main className="flex-grow container mx-auto px-4 md:px-8 max-w-7xl pb-20 relative">
        {/* SEARCH PHASE */}
        {phase === PHASE.SEARCH && (
          <section className="flex flex-col items-center justify-center min-h-[50vh] animate-fade-in-up">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-brand-soft text-brand-orange text-xs font-bold tracking-wider mb-6 animate-float">
              <span className="w-2 h-2 rounded-full bg-brand-orange"></span> AI SHOPPING AGENT
            </div>

            <h1 className="font-display text-4xl md:text-7xl font-bold text-center mb-6 leading-tight text-brand-black">
              Find the best.<br />
              Without the{' '}
              <span className="text-brand-orange relative inline-block">
                noise.
                <svg className="absolute w-full h-3 -bottom-1 left-0 text-brand-orange opacity-40" viewBox="0 0 200 9" fill="none">
                  <path d="M2 7C26 2.5 132.5-1.5 198 2.5" stroke="currentColor" strokeWidth="3" />
                </svg>
              </span>
            </h1>

            <form onSubmit={handleSearch} className="w-full max-w-2xl relative group mb-12">
              <div className="absolute inset-y-0 left-6 flex items-center pointer-events-none">
                <i className="fa-solid fa-magnifying-glass text-xl text-gray-400 group-focus-within:text-brand-orange transition-colors"></i>
              </div>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="w-full py-5 pl-14 pr-36 bg-white border border-gray-200 rounded-2xl shadow-xl shadow-gray-200/40 text-lg focus:outline-none focus:ring-4 focus:ring-brand-orange/10 focus:border-brand-orange transition-all"
                placeholder="e.g., Best espresso machine under $500..."
                required
              />
              <button
                type="submit"
                className="absolute right-3 top-2.5 bottom-2.5 bg-brand-black hover:bg-brand-orange text-white font-medium px-6 rounded-xl transition-all duration-300 flex items-center gap-2"
              >
                Search
              </button>
            </form>

            {/* Search History */}
            <SearchHistory
              history={history}
              loading={historyLoading}
              onView={handleViewHistory}
              onDelete={handleDeleteHistory}
              onReSearch={(q) => { setQuery(q); }}
            />
          </section>
        )}

        {/* PERSONALIZATION PHASE */}
        {phase === PHASE.PERSONALIZE && (
          <PersonalizationModal
            questions={questions}
            onSubmit={handleSubmitPersonalization}
            onSkip={handleSkipPersonalization}
          />
        )}

        {/* LOADING PHASE */}
        {phase === PHASE.LOADING && (
          <LoadingTerminal logs={logs} elapsed={elapsed} />
        )}

        {/* RESULTS PHASE */}
        {phase === PHASE.RESULTS && results && (
          <ResultsView
            results={results}
            products={products}
            onOpenDrawer={setDrawerProduct}
            onNewSearch={resetToSearch}
          />
        )}
      </main>

      {/* Product drawer */}
      {drawerProduct && (
        <ProductDrawer product={drawerProduct} onClose={() => setDrawerProduct(null)} />
      )}
    </div>
  );
}
