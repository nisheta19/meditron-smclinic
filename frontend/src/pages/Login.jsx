import { useEffect, useState } from 'react';
import { loginAccount } from '../api/auth';
import background from '../assets/auth/background.png';
import doctor from '../assets/auth/doctor.png';
import logo from '../assets/auth/logo.svg';
import './Login.css';

export default function Login({ onLogin, checking = false }) {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [viewport, setViewport] = useState(() => ({ width: innerWidth, height: innerHeight }));
  useEffect(() => {
    const resize = () => setViewport({ width: innerWidth, height: innerHeight });
    addEventListener('resize', resize);
    return () => removeEventListener('resize', resize);
  }, []);
  const scale = viewport.width >= 900 ? viewport.width / 1280 : 1;
  const submit = async event => {
    event.preventDefault();
    if (busy || checking) return;
    setBusy(true); setError('');
    try { onLogin(await loginAccount(login.trim(), password)); }
    catch (failure) {
      setError(failure.status === 401 ? 'Неверный логин или пароль' : 'Не удалось войти. Попробуйте ещё раз.');
    } finally { setBusy(false); }
  };

  return <main className="auth" style={{ '--auth-scale': scale, '--auth-height': `${viewport.height / scale}px` }}>
    <div className="auth-stage">
      <img className="auth-background" src={background} alt="" />
      <img className="auth-logo" src={logo} alt="СМ-Клиника" />
      <img className="auth-doctor" src={doctor} alt="" />
      <form className="auth-card" onSubmit={submit} aria-label="Вход в систему" aria-busy={busy || checking}>
        <h1>Добро пожаловать</h1>
        <p className="auth-intro">Пожалуйста, введите данные аккаунта<br />для доступа в систему</p>
        <label className="auth-field auth-login">
          <span>Логин</span>
          <input name="login" autoComplete="username" placeholder="loginexample" value={login} maxLength={128}
            onChange={event => { setLogin(event.target.value); setError(''); }} required aria-invalid={error ? true : undefined} />
        </label>
        <label className="auth-field auth-password">
          <span>Пароль</span>
          <input name="password" type="password" autoComplete="current-password" value={password} maxLength={128}
            onChange={event => { setPassword(event.target.value); setError(''); }} required aria-invalid={error ? true : undefined}
            aria-describedby={error ? 'auth-error' : undefined} />
          {!password && <span className="auth-dots" aria-hidden="true">{Array.from({ length: 9 }, (_, index) => <i key={index} />)}</span>}
        </label>
        <button type="submit" className="auth-submit" disabled={busy || checking}>Войти в систему</button>
        {error && <p id="auth-error" className="auth-error" role="alert">{error}</p>}
      </form>
    </div>
  </main>;
}
