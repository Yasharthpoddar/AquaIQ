import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Home from './pages/Home';
import DistrictDetail from './pages/DistrictDetail';
import Alerts from './pages/Alerts';
import Simulate from './pages/Simulate';
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
            <NavLink to="/" end>Home</NavLink>
            <NavLink to="/alerts">Alerts</NavLink>
            <NavLink to="/simulate">Simulate</NavLink>
          </div>
        </nav>
        <main className="main-content">
          <Routes>
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
