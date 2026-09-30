import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

import { LoginPage } from './session/LoginPage';
import { useSession } from './session/session';
import { Console } from './shell/Console';

export function App() {
  const session = useSession((s) => s.session);
  const [queries] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 30_000 } } }),
  );

  return (
    <QueryClientProvider client={queries}>
      {session ? <Console key={session.token} session={session} /> : <LoginPage />}
    </QueryClientProvider>
  );
}
