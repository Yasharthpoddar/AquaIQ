import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Home from './pages/Home';
import DistrictDetail from './pages/DistrictDetail';
import Alerts from './pages/Alerts';
import Simulate from './pages/Simulate';
import ResearchForecast from './components/ResearchForecast';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="nav-bar">
          <div className="nav-brand">
            <span className="nav-logo">💧</span>
            <span className="nav-title">AquaIQ</span>
          </div>
          <div className="nav-links">
            <NavLink to="/research">Research</NavLink>
            <NavLink to="/" end>Home</NavLink>
            <NavLink to="/alerts">Alerts</NavLink>
            <NavLink to="/simulate">Simulate</NavLink>
          </div>
        </nav>
        <main className="main-content">
          <aside className="card" aria-label="Research prototype limitations" style={{padding:'1rem',marginBottom:'1rem'}}>
            <strong>Academic research prototype · primary horizon: 12 calendar months.</strong> Direct M+12 research estimates and an annual baseline are separate from the legacy six-month products. Nationwide accuracy and real-time forecasting skill have not been verified. The 0–100 score is a project-defined, uncalibrated risk index, not a crisis probability or an official groundwater classification.
          </aside>
          <Routes>
            <Route path="/research" element={<div className="page"><h1>Twelve-month groundwater research</h1><ResearchForecast /></div>} />
            <Route path="/" element={<Home />} />
            <Route path="/district/:id" element={<DistrictDetail />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/simulate" element={<Simulate />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
