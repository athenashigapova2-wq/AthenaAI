import React, { createContext, useState, useContext, useEffect } from 'react';
import { Browser } from '@capacitor/browser';
import { Capacitor } from '@capacitor/core';
import { supabase } from '@/api/supabaseClient';
import { authRedirectUrl, registerNativeAuthCallbacks } from '@/lib/authCallbacks';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [authError, setAuthError] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    // Первичная проверка текущей сессии
    checkUserAuth();

    // Подписка на изменения сессии (логин/логаут/обновление токена в других вкладках)
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
      setIsAuthenticated(!!session?.user);
      setAuthChecked(true);
    });

    const unregisterNativeCallbacks = registerNativeAuthCallbacks((error) => {
      console.error('Auth callback failed:', error);
      setAuthError({ type: 'auth_callback', message: error.message });
    });

    return () => {
      listener?.subscription?.unsubscribe();
      unregisterNativeCallbacks();
    };
  }, []);

  const checkUserAuth = async () => {
    try {
      setIsLoadingAuth(true);
      const { data, error } = await supabase.auth.getSession();
      if (error) throw error;
      setUser(data.session?.user ?? null);
      setIsAuthenticated(!!data.session?.user);
    } catch (error) {
      console.error('Auth check failed:', error);
      setAuthError({ type: 'unknown', message: error.message });
      setUser(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoadingAuth(false);
      setAuthChecked(true);
    }
  };

  // ---- Методы, повторяющие интерфейс base44.auth.* -------------------------

  const loginViaEmailPassword = async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    return data.user;
  };

  const register = async (email, password, fullName) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        emailRedirectTo: authRedirectUrl('callback'),
      },
    });
    if (error) throw error;
    return data.user;
  };

  const loginWithProvider = async (provider = 'google') => {
    const native = Capacitor.isNativePlatform();
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: authRedirectUrl('callback'),
        skipBrowserRedirect: native,
      },
    });
    if (error) throw error;
    if (native) {
      if (!data?.url) throw new Error('OAuth provider did not return an authorization URL');
      await Browser.open({ url: data.url });
    }
  };

  const verifyOtp = async (email, token) => {
    const { data, error } = await supabase.auth.verifyOtp({ email, token, type: 'signup' });
    if (error) throw error;
    return data;
  };

  const resendOtp = async (email) => {
    const { error } = await supabase.auth.resend({ type: 'signup', email });
    if (error) throw error;
  };

  const resetPasswordRequest = async (email) => {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: authRedirectUrl('reset-password'),
    });
    if (error) throw error;
  };

  const resetPassword = async (newPassword) => {
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
  };

  const logout = async () => {
    await supabase.auth.signOut();
    setUser(null);
    setIsAuthenticated(false);
  };

  const navigateToLogin = () => {
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoadingAuth,
        isLoadingPublicSettings: false, // не нужно с Supabase — оставлено для обратной совместимости
        authError,
        authChecked,
        loginViaEmailPassword,
        register,
        loginWithProvider,
        verifyOtp,
        resendOtp,
        resetPasswordRequest,
        resetPassword,
        logout,
        navigateToLogin,
        checkUserAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
