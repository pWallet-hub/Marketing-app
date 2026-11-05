import { createContext, useContext } from 'react';

// The signed-in person (from /api/me), with isAdmin added. Null outside the signed-in shell.
export const UserContext = createContext(null);
export const useUser = () => useContext(UserContext);
