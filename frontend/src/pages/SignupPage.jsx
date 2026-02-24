import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { signup } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export default function SignupPage() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { loginWith } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await signup(name, email, password);
      loginWith(data.token, data.user);
      navigate('/');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-beige-50 px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-10">
          <div className="w-12 h-12 bg-brand-black rounded-xl flex items-center justify-center text-white shadow-lg shadow-brand-orange/20">
            <i className="fa-solid fa-layer-group text-xl"></i>
          </div>
          <span className="font-display font-bold text-3xl tracking-tight">MAVEN</span>
        </div>

        <div className="bg-white rounded-3xl shadow-xl shadow-gray-200/50 border border-gray-100 p-8">
          <h2 className="font-display text-2xl font-bold text-brand-black mb-1">Create account</h2>
          <p className="text-gray-500 text-sm mb-8">Join Maven to get personalized shopping recommendations</p>

          {error && (
            <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-100 text-red-600 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full py-3 px-4 bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-brand-orange/10 focus:border-brand-orange transition-all"
                placeholder="Your name"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full py-3 px-4 bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-brand-orange/10 focus:border-brand-orange transition-all"
                placeholder="you@example.com"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full py-3 px-4 bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-4 focus:ring-brand-orange/10 focus:border-brand-orange transition-all"
                placeholder="At least 6 characters"
                minLength={6}
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 bg-brand-black text-white rounded-xl font-medium hover:bg-brand-orange transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-brand-black/20"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Creating account...
                </span>
              ) : 'Create account'}
            </button>
          </form>

          <p className="text-center text-sm text-gray-500 mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-brand-orange font-medium hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
