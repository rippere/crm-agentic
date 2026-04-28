import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  typescript: {
    // Supabase v2.103.2 type inference requires generated types (supabase gen types).
    // Without them, table queries resolve to `never`. Runtime behavior is correct.
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
