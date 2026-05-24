FROM node:22-slim AS builder
WORKDIR /app

RUN npm install -g pnpm

# pnpm-workspace.yaml carries the `onlyBuiltDependencies` allowlist
# (protobufjs needs its postinstall to compile descriptors). Without
# it in the build context, pnpm 10+ exits with ERR_PNPM_IGNORED_BUILDS.
# Also pin a known-good pnpm via packageManager / corepack later if
# this drifts again.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# ---------------------------------------------------------------------------
FROM node:22-slim
WORKDIR /app

COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

EXPOSE 3000
CMD ["node", "build"]
