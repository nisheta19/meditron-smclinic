// Признак входа на этом устройстве. Сама сессия — cookie backend; здесь только подсказка «был вход»,
// чтобы после перезагрузки сразу проверить GET /api/auth/me, а не показывать форму.
const KEY = 'sm-route:auth';
export const session = {
  has: () => { try { return !!localStorage.getItem(KEY); } catch { return false; } },
  save: (account) => { try { localStorage.setItem(KEY, JSON.stringify({ ...account, at: Date.now() })); } catch { /* приватный режим */ } },
  clear: () => { try { localStorage.removeItem(KEY); } catch { /* нет хранилища */ } },
};
