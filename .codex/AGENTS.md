# Project Development Rules for Codex

## 1. Architecture Decision: Model Factory Must Use Strategy + Registry

For this project, all model construction logic must follow the **Strategy + Registry** pattern as the primary architecture.

Do **not** use Builder Pattern as the default solution for model/provider construction unless explicitly requested and justified.

The intended design is:

- Factory only decides **which strategy to use**.
- Strategy handles **how to build provider-specific models**.
- Registry manages **which provider strategies are available**.
- Context carries runtime configuration, model type, fallback chain, and shared dependencies.

Conceptual responsibility split:

```text
Factory  = select strategy + pass context + return model
Strategy = build provider-specific chat / embedding model
Registry = register and retrieve strategies by provider / MODEL_TYPE
Context  = carry config, environment, fallback chain, runtime options