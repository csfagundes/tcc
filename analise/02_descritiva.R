# ============================================================
# 02_descritiva.R — Descriptive statistics and contingency tables
# ============================================================

library(tidyverse)
library(janitor)

df          <- readRDS("analise/df_cartoes.rds")
df_jogadores <- readRDS("analise/df_jogadores.rds")

# ── 1. Card counts by race ─────────────────────────────────
cat("\n=== Cartoes por raca ===\n")
df |>
  count(raca, card_type) |>
  pivot_wider(names_from = card_type, values_from = n, values_fill = 0) |>
  print()

# ── 2. Card rates per player by race ──────────────────────
cat("\n=== Taxa media de cartoes por jogador (por raca) ===\n")
df_jogadores |>
  group_by(raca) |>
  summarise(
    n_jogadores      = n(),
    media_amarelos   = mean(n_amarelos),
    media_vermelhos  = mean(n_vermelhos),
    mediana_amarelos = median(n_amarelos),
    .groups = "drop"
  ) |>
  print()

# ── 3. By position ────────────────────────────────────────
cat("\n=== Cartoes por posicao e raca ===\n")
df |>
  filter(!is.na(raca), !is.na(position)) |>
  count(raca, position, card_type) |>
  pivot_wider(names_from = card_type, values_from = n, values_fill = 0) |>
  arrange(position, raca) |>
  print(n = 60)

# ── 4. By season ──────────────────────────────────────────
cat("\n=== Cartoes por temporada e raca ===\n")
df |>
  filter(!is.na(raca)) |>
  count(season, raca) |>
  pivot_wider(names_from = raca, values_from = n, values_fill = 0) |>
  print()

# ── 5. Home vs Away ───────────────────────────────────────
cat("\n=== Cartoes por home_away e raca ===\n")
df |>
  filter(!is.na(raca)) |>
  count(home_away, raca) |>
  pivot_wider(names_from = raca, values_from = n, values_fill = 0) |>
  print()

cat("\nDescritiva concluida.\n")
