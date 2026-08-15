import { AppRouter } from "./router";
import { Providers } from "./providers";

export function App() {
  return (
    <Providers>
      <AppRouter />
    </Providers>
  );
}
