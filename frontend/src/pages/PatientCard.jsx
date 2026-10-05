import { useState } from 'react';
import { api, USE_MOCK } from '../api';
import { go, useAsync } from '../lib/hooks';
import { Dialog, ErrorBox } from '../components/ui';
import ProtocolReview, { MoreDialog, StandaloneFindingReview } from '../components/ProtocolReview';
import ClinicalNotifyDialog from '../components/ClinicalNotifyDialog';
import { PatientCardPage, RouteDetails } from '../components/patient-card/PatientCardView';
import { fromFinalPatient } from '../components/patient-card/fromFinalPatient';

export default function PatientCard({ id }) {
  const card = useAsync(() => api.patient(id), [id], { refreshMs:15000 });
  const notifications = useAsync(() => api.patientNotifications(id), [id], { refreshMs:15000 });
  const [dialog, setDialog] = useState(null);
  const [protocolId, setProtocolId] = useState(null);
  const [allHistory, setAllHistory] = useState(false);
  const reload = () => { card.reload(); notifications.reload(); };
  if (card.error) return <ErrorBox error={card.error} onRetry={card.reload} />;
  if (!card.data) return <p className="state">Загружаем карточку пациента…</p>;
  const c = card.data;
  const patient = fromFinalPatient(c, { notifications:notifications.data ?? [] });
  const history = patient.history;
  const routes = (c.clinicalRoutes ?? []).filter(r => r.open && r.chainType !== 'EMERGENCY');
  const emergency = c.currentFindings.some(f => !['REJECTED','REMOVED'].includes(f.status) && f.level === 'EMERGENCY');
  const openProtocol = protoId => { setProtocolId(protoId); window.scrollTo(0,0); };
  const saveReview = async () => {
    const fresh = await api.patient(id);
    reload();
    const available = (fresh.clinicalRoutes ?? []).filter(r => r.open && r.chainType !== 'EMERGENCY');
    const hasEmergency = fresh.currentFindings.some(f => !['REJECTED','REMOVED'].includes(f.status) && f.level === 'EMERGENCY');
    if (!available.length || hasEmergency || USE_MOCK) throw new Error('Нет доступного маршрута для уведомления.');
    setDialog({type:'notify',routes:available});
  };
  return <>
    <PatientCardPage patient={{...patient, history:allHistory ? history : history.slice(0,10)}}
      onClose={() => protocolId ? setProtocolId(null) : go('findings')} onSearch={query => query.trim() && go(`findings?q=${encodeURIComponent(query.trim())}`)}
      onMore={() => setDialog({type:'more'})}
      onFindingOpen={finding => finding.source.protocolId ? openProtocol(finding.source.protocolId) : setDialog({type:'finding',finding:finding.source})}
      onHistoryOpen={event => event.kind === 'route' ? setDialog({type:'route',event}) : openProtocol(event.source.id)}
      onHistoryMore={!allHistory && history.length > 10 ? () => setAllHistory(true) : undefined}
      onNotify={!USE_MOCK && routes.length && !emergency && !notifications.error ? () => setDialog({type:'notify'}) : undefined}
      notificationsState={notifications.error ? <ErrorBox error={notifications.error} onRetry={notifications.reload} /> : !notifications.data ? <p className="npc-empty">Загружаем уведомления…</p> : null}
      onNotificationOpen={notification => setDialog({type:'message',notification})}>
      {protocolId && <ProtocolReview key={protocolId} card={c} protocolId={protocolId} routes={patient.routes.filter(r => r.source.protocolId === protocolId)} onChanged={reload} onSave={saveReview} />}
    </PatientCardPage>
    {dialog?.type === 'finding' && <StandaloneFindingReview finding={dialog.finding} onChanged={reload} onClose={() => setDialog(null)} />}
    {dialog?.type === 'more' && <PatientMore card={c} protocolId={protocolId} onClose={() => setDialog(null)} />}
    {dialog?.type === 'notify' && <ClinicalNotifyDialog routes={dialog.routes ?? routes} onClose={() => setDialog(null)} onDone={reload} />}
    {dialog?.type === 'route' && <Dialog title={dialog.event.title} wide onClose={() => setDialog(null)}>
      <p>{dialog.event.source.stageTitle}</p><div className="npc-card-detail"><RouteDetails details={dialog.event.details} /></div>
    </Dialog>}
    {dialog?.type === 'message' && <Dialog title="Уведомление" onClose={() => setDialog(null)}>
      <p>{dialog.notification.message}</p><p>{dialog.notification.route} · {dialog.notification.sent}</p>
      <p>Статус: {({SENT:'Отправлено в CRM',DELIVERED:'Доставлено',READ:'Прочитано',FAILED:'Ошибка доставки'})[dialog.notification.source.delivery] ?? '—'}</p>
      <p>Прочитано: {dialog.notification.read ?? '—'}</p>
    </Dialog>}
  </>;
}

function PatientMore({card, protocolId, onClose}) {
  const selectedId = protocolId ?? card.currentProtocol?.id;
  const protocol = useAsync(() => selectedId ? api.protocol(selectedId) : Promise.resolve(null), [selectedId]);
  if (protocol.error) return <Dialog title="Данные пациента" onClose={onClose}><ErrorBox error={protocol.error} onRetry={protocol.reload} /></Dialog>;
  return <MoreDialog c={card} protocol={protocol.data} names={{}} onClose={onClose} />;
}
