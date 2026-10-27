import type {User} from '../services/api';

// Workspace Owner/Admin never grants platform administration.
export const isPlatformAdmin = (user: User) => user.is_platform_admin === true && user.email_verified && user.status === 'active';
export const loginDestination = (user: User) => isPlatformAdmin(user) ? '/admin' : '/projects';
