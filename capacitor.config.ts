import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'dev.aminashigapova2.athena',
  appName: 'Athena',
  webDir: 'dist',
};

export default config;

const config: CapacitorConfig = {
  appId: 'dev.aminashigapova2.athena',
  appName: 'Athena',
  webDir: 'dist',

  // Только для локальной разработки через Android Emulator
  server: {
    androidScheme: 'http',
    cleartext: true,
  },
};