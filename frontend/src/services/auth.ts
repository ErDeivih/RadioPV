import axios from '../axios';
import { toUser } from '../api/adapt';
import type { MeOut } from '../api/types';

const fetchUser = () => axios.get<MeOut>('/auth/me').then((r) => ({ data: toUser(r.data) }));

export const authService = {
  fetchUser,
};
