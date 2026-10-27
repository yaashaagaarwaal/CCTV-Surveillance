import { Link } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import Logo from '../Logo'

export default function Footer() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  return (
    <footer className="border-t border-white/[0.07] bg-black/30">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr] lg:px-8">
        <div>
          <Logo />
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-500">
            Smart AI-Based Home CCTV Surveillance System. Real-time person detection, face recognition, night surveillance and explainable alerts — running locally.
          </p>
        </div>
        <nav aria-label="Footer">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">Explore</p>
          <ul className="mt-4 space-y-2.5 text-sm text-slate-500">
            <li><a href="#top" className="hover:text-sky-300">Home</a></li>
            <li><a href="#features" className="hover:text-sky-300">Features</a></li>
            <li><a href="#how-it-works" className="hover:text-sky-300">How It Works</a></li>
            <li><a href="#about" className="hover:text-sky-300">About</a></li>
          </ul>
        </nav>
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">Access</p>
          <ul className="mt-4 space-y-2.5 text-sm text-slate-500">
            <li>
              <Link to={signedIn ? '/dashboard' : '/login'} className="hover:text-sky-300">
                {signedIn ? 'Dashboard' : 'Login'}
              </Link>
            </li>
            <li className="text-slate-600">Accounts are created by the administrator</li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/[0.05] px-4 py-5 text-center text-xs text-slate-600">
        © {new Date().getFullYear()} Smart AI-Based Home CCTV Surveillance System · A 3rd-year college project · Python · FastAPI · OpenCV · YOLOv8 · React
      </div>
    </footer>
  )
}
