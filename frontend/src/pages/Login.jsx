// Страница авторизации по макету Figma (auth.fig, кадр «Авторизация»).
// Вход: POST /api/auth/login (cookie-сессия backend). В демо-режиме подходит любой логин и пароль. Выход — в меню профиля.
import { useState } from 'react';
import { api } from '../api';
import { session } from '../api/session';
import { Logo } from '../components/Icons';
import background from '../assets/auth/background.webp';
import doctor from '../assets/auth/doctor.webp';

/** Выход: закрыть сессию на backend и забыть её здесь — App покажет страницу авторизации */
export async function logout() {
  await api.logout().catch(() => null);
  session.clear();
}

export default function Login({ onLogin }) {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      // backend: POST /api/auth/login (cookie-сессия); в демо-режиме подходит любой логин и пароль
      const account = await api.login({ login: login.trim(), password });
      session.save(account);
      onLogin(account);
    } catch (err) {
      setBusy(false);
      setError(err.status === 401 || err.status === 400 ? 'Неверный логин или пароль' : err.message);
    }
  };

  return (
    <div className="auth" style={{ backgroundImage: `url(${background})` }}>
      <div className="auth-art" aria-hidden="true">
        <Logo height={63} />
        <img src={doctor} alt="" className="auth-doctor" />
      </div>

      <form className="auth-card" onSubmit={submit}>
        <div className="auth-head">
          <h1>Добро пожаловать</h1>
          <p>Пожалуйста, введите данные аккаунта для доступа в систему</p>
        </div>
        <label className="auth-field">
          <span>Логин</span>
          <input name="login" autoComplete="username" placeholder="loginexample" value={login} onChange={(e) => setLogin(e.target.value)} autoFocus />
        </label>
        <label className="auth-field">
          <span>Пароль</span>
          <input name="password" type="password" autoComplete="current-password" placeholder="●●●●●●●●●" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button type="submit" className="btn-main auth-submit" disabled={busy}>{busy ? 'Входим…' : 'Войти в систему'}</button>
      </form>
    </div>
  );
}
