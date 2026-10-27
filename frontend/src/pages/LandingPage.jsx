import About from '../components/landing/About'
import Features from '../components/landing/Features'
import Footer from '../components/landing/Footer'
import Hero from '../components/landing/Hero'
import HowItWorks from '../components/landing/HowItWorks'
import Navbar from '../components/landing/Navbar'

// Public marketing page. It makes no API calls except the session check
// (done once by AuthProvider) used to show "Dashboard" instead of "Login".
export default function LandingPage() {
  return (
    <div className="min-h-screen overflow-x-clip bg-ink text-slate-200">
      <Navbar />
      <main>
        <Hero />
        <Features />
        <HowItWorks />
        <About />
      </main>
      <Footer />
    </div>
  )
}
