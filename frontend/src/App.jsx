import Navbar from './components/Navbar';
import Hero from './components/Hero';
import Pipeline from './components/Pipeline';
import DashboardSection from './components/DashboardSection';
import ResumeUpload from './components/ResumeUpload';
import Footer from './components/Footer';

export default function App() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <Pipeline />
        <DashboardSection />
        <ResumeUpload />
      </main>
      <Footer />
    </>
  );
}
