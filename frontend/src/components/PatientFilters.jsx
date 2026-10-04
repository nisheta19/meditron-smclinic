import { AGE_GROUPS, SEX, URGENCY } from '../lib/patientFilters';
import { Select } from './ui';

/** Четыре фильтра панели под иконкой настроек. pathologies: [[code, name]] — только те, что есть в списке */
export default function PatientFilters({ value: f, onChange, pathologies }) {
  const set = (k) => (v) => onChange({ ...f, [k]: v });
  return (
    <>
      <Select label="Пол" value={f.sex} onChange={set("sex")} options={SEX} all="Любой" />
      <Select label="Возраст" value={f.age} onChange={set('age')} options={AGE_GROUPS.map(([k, l]) => [k, l])} all="Любой" />
      <Select label="Патология" value={f.pathology} onChange={set('pathology')} options={pathologies} all="Любая" />
      <Select label="Срочность" value={f.urgency} onChange={set('urgency')} options={URGENCY} all="Любая" />
    </>
  );
}
