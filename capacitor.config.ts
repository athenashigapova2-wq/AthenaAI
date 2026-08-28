import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'dev.aminashigapova2.athena',
  appName: 'Athena',
  webDir: 'dist',
  // Keep WebView logs limited to warnings/errors in packaged builds.
  loggingBehavior: 'production',
  server: {
    // Packaged assets use Capacitor's secure local origin: https://localhost.
    androidScheme: 'https',
    cleartext: false,
  },
  android: {
    allowMixedContent: false,
  },
};

export default config;
