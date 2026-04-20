# ============================================================
# 01_carregar_dados.R — Load Excel, derive variables, save RDS
# ============================================================

library(tidyverse)
library(readxl)
library(janitor)

ARQUIVO <- here::here("cartoes_com_raca.xlsx")
if (!file.exists(ARQUIVO)) ARQUIVO <- "../cartoes_com_raca.xlsx"

df_raw <- read_excel(ARQUIVO) |> clean_names()

# Standardise column names that may differ by extractor version
df <- df_raw |>
  rename_with(~ gsub("classificacao", "raca", .x)) |>
  mutate(
    raca       = factor(raca,     levels = c("Branco", "Pardo", "Preto")),
    confianca  = factor(confianca, levels = c("alta", "media", "baixa")),
    card_type  = factor(card_type, levels = c("yellow", "yellow_red", "red")),
    season     = as.integer(season),
    home_away  = factor(home_away, levels = c("home", "away")),
    position   = factor(position),
    # Binary outcome flags
    cartao_vermelho = as.integer(card_type %in% c("red", "yellow_red")),
    # Score context at time of card
    score_diff = as.numeric(score_home_at_card) - as.numeric(score_away_at_card),
    perdendo_jogo  = case_when(
      home_away == "home" ~ as.integer(score_diff < 0),
      home_away == "away" ~ as.integer(score_diff > 0),
      TRUE ~ NA_integer_
    ),
    vencendo_jogo  = case_when(
      home_away == "home" ~ as.integer(score_diff > 0),
      home_away == "away" ~ as.integer(score_diff < 0),
      TRUE ~ NA_integer_
    )
  )

# Player-level aggregate (for negative binomial)
df_jogadores <- df |>
  group_by(player_id, player_name, raca, position) |>
  summarise(
    n_amarelos  = sum(card_type == "yellow",       na.rm = TRUE),
    n_vermelhos = sum(cartao_vermelho == 1,         na.rm = TRUE),
    n_total     = n(),
    .groups = "drop"
  )

saveRDS(df,          "analise/df_cartoes.rds")
saveRDS(df_jogadores,"analise/df_jogadores.rds")

cat("Dados carregados:", nrow(df), "cartoes,",
    df |> pull(player_id) |> n_distinct(), "jogadores unicos.\n")
cat("Racas:\n")
print(table(df$raca, useNA = "ifany"))
