// Only the requested menu is reproduced; no patient mockup contents are imported.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/inter';
import '../src/styles.css';
import '../src/design.css';
import '../src/pages/Login.css';
import DoctorMenu from '../src/components/DoctorMenu';
function Fixture() {
  const [open, setOpen] = useState(false);
  return <div className="layout"><aside className="sidebar"><div className={`nav-bottom${open ? ' profile-open' : ''}`}>
    <DoctorMenu name="Фамимилия И. О." onOpenChange={setOpen} onLogout={() => {}} />
    <button className="nav-item faint">Свернуть</button>
  </div></aside></div>;
}
createRoot(document.getElementById('root')).render(<Fixture />);
