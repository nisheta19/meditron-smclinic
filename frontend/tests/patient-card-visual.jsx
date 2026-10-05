// Development-only visual harness; never imported by the application entry point.
import React from 'react';
import { createRoot } from 'react-dom/client';
import '../src/styles.css';
import '../src/design.css';
import { PatientCardPage } from '../src/components/patient-card/PatientCardView';
import { fixture } from './patient-card-design-fixture';
import ProtocolReview from '../src/components/ProtocolReview';
import ClinicalNotifyDialog from '../src/components/ClinicalNotifyDialog';
import '../src/workspace-scale.css';
const mode = new URLSearchParams(location.search).get('mode');
const routes = [fixture.routes[0], {...fixture.routes[0],id:'route-4'}];
createRoot(document.getElementById('root')).render(<div className="layout patient-view"><main className="main">
  <PatientCardPage patient={fixture} initialExpandedRouteId="route-2">
    {mode === 'review' && <ProtocolReview card={{id:'visual-patient',currentProtocol:{id:'visual-protocol'},history:{protocols:[]}}} protocolId="visual-protocol" routes={routes} onChanged={()=>{}} onSave={()=>{}} />}
  </PatientCardPage>
  {mode === 'notify' && <ClinicalNotifyDialog routes={[{id:'route-1',specialty:'Оперирующий гинеколог'}]} onClose={()=>{}} onDone={()=>{}} />}
</main></div>);
