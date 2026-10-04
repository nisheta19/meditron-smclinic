import { USE_MOCK } from '../api';
import Patients from './Patients';
import DemoFindings from './DemoFindings';

export default function Findings() {
  return USE_MOCK ? <DemoFindings /> : <Patients preset="findings" />;
}
