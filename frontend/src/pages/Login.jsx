// Страница авторизации по макету Figma (auth.fig, кадр «Авторизация»).
// Пока заглушка: вход при любом логине и пароле, выхода нет. Сессия хранится в localStorage.
import { useState } from 'react';
import { Logo } from '../components/Icons';
import background from '../assets/auth/background.webp';
import doctor from '../assets/auth/doctor.webp';

const KEY = 'sm-route:auth';

/** Вошёл ли пользователь (переживает перезагрузку страницы) */
export const isAuthed = () => { try { return !!localStorage.getItem(KEY); } catch { return false; } };
const remember = (login) => { try { localStorage.setItem(KEY, JSON.stringify({ login, at: Date.now() })); } catch { /* приватный режим — вход до перезагрузки */ } };

export default function Login({ onLogin }) {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = (e) => {
    e.preventDefault();
    setBusy(true);
    remember(login.trim());
    setTimeout(() => onLogin(login.trim()), 250);   // короткая пауза — кнопка успевает показать нажатие
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
        <button type="submit" className="btn-main auth-submit" disabled={busy}>{busy ? 'Входим…' : 'Войти в систему'}</button>
      </form>
    </div>
  );
}
