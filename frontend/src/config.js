// Настройки интерфейса. Авторизации в API пока нет — имя врача передаётся в поле doctor.
export const CURRENT_DOCTOR = import.meta.env.VITE_DOCTOR_NAME || 'Демо-врач';
export const DOCTOR_DISPLAY_NAME = import.meta.env.VITE_DOCTOR_NAME || 'Фамилия И. О.';
export const PAGE_SIZE = 50;
