FROM node:22-slim AS builder
WORKDIR /app

# Use corepack so the pnpm version comes from package.json's
# `packageManager` field — deterministic, no `npm install -g pnpm`
# drift between local + CI.
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# pnpm 10.13.x treats unallowlisted transitive install scripts
# (protobufjs, pulled in by centrifuge) as a warning. Newer pnpm
# (10.16+ / 11.x) escalated this to a fatal `ERR_PNPM_IGNORED_BUILDS`,
# which silently broke this image when `npm install -g pnpm` started
# pulling a newer release. The `packageManager` pin in package.json +
# corepack above guarantees 10.13.1 here.
#
# If you bump the pnpm pin past the strictness change, you'll also need
# to regenerate pnpm-lock.yaml so its `settings.onlyBuiltDependencies`
# snapshot includes `protobufjs` (and `esbuild`) — workspace.yaml alone
# isn't enough under --frozen-lockfile.
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
