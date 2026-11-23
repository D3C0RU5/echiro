# echiro

Monorepo com API em Python/FastAPI e aplicação web em React/TypeScript/Vite.

## Dev Container

Abra esta pasta no VS Code com a extensão **Dev Containers** e execute **Dev Containers: Reopen in Container**. A criação do container instala Node.js 22, Python 3.12, `uv` e as dependências dos dois projetos.

Depois, execute `npm run dev:api` e `npm run dev:web` em dois terminais do container. As portas 8000 e 5173 são encaminhadas automaticamente.

## Pré-requisitos

- Python 3.12 ou superior
- [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ ou 22.12+ e npm

## Instalação

```bash
npm install
cd apps/api && uv sync && cd ../..
```

## Desenvolvimento

Em dois terminais, na raiz do projeto:

```bash
npm run dev:api
```

```bash
npm run dev:web
```

- Aplicação web: http://localhost:5173
- API: http://localhost:8000/api/health
- Documentação interativa da API: http://localhost:8000/docs

O Vite encaminha as chamadas `/api` para o FastAPI durante o desenvolvimento.

## Build do frontend

```bash
npm run build
```

O resultado fica em `apps/web/dist`.
