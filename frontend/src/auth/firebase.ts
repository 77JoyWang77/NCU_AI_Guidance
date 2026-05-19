import { initializeApp } from 'firebase/app';
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  type User,
} from 'firebase/auth';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const app = initializeApp(firebaseConfig);

export const firebaseAuth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

export function signInWithGoogle() {
  return signInWithPopup(firebaseAuth, googleProvider);
}

export function signOutOfFirebase() {
  return signOut(firebaseAuth);
}

export function getFirebaseIdToken(user?: User | null): Promise<string | null> {
  const currentUser = user ?? firebaseAuth.currentUser;
  if (!currentUser) return Promise.resolve(null);
  return currentUser.getIdToken();
}
