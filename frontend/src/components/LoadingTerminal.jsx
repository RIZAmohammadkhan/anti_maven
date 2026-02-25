import { useRef, useEffect } from 'react';

function formatTime(ms) {
  const seconds = Math.floor(ms / 1000);
  const milliseconds = Math.floor((ms % 1000) / 100);
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}.${milliseconds}`;
}

export default function LoadingTerminal({ logs, elapsed }) {
  const logsEndRef = useRef(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const latestLog = logs.length > 0 ? logs[logs.length - 1].text : 'Initializing agent graph...';

  return (
    <section className="flex flex-col items-center justify-center py-10 min-h-[60vh] animate-fade-in-up">
      {/* Timer */}
      <div className="flex items-center gap-3 mb-8">
        <div className="w-3 h-3 bg-brand-orange rounded-full animate-pulse"></div>
        <span className="font-mono text-xl font-bold text-brand-black">{formatTime(elapsed)}</span>
      </div>

      <div className="relative w-full max-w-2xl">
        {/* Main Status */}
        <div className="text-center mb-8">
          <h3 className="font-display text-2xl font-bold mb-2">Maven is working</h3>
          <p className="text-gray-500">{latestLog}</p>
        </div>

        {/* Live Terminal */}
        <div className="bg-[#1e1e1e] rounded-xl shadow-2xl overflow-hidden border border-gray-800 w-full">
          <div className="bg-[#2d2d2d] px-4 py-2 flex items-center gap-2 border-b border-gray-700">
            <div className="w-3 h-3 rounded-full bg-red-500"></div>
            <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
            <div className="w-3 h-3 rounded-full bg-green-500"></div>
            <span className="ml-2 text-xs text-gray-400 font-mono">agent_stream.log</span>
          </div>
          <div className="p-4 h-64 overflow-y-auto font-mono text-sm terminal-scroll space-y-2">
            {logs.map((entry, idx) => (
              <div key={idx} className="text-green-400 animate-fade-in-up">
                <span className="text-gray-500 mr-2">
                  [{entry.time.toLocaleTimeString().split(' ')[0]}]
                </span>
                {'> '}
                <span
                  dangerouslySetInnerHTML={{
                    __html: entry.text.replace(
                      /(Manager|Researcher|Specialist|Formatter|Agent)/g,
                      '<span class="text-blue-400 font-bold">$1</span>'
                    ),
                  }}
                />
              </div>
            ))}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    </section>
  );
}
