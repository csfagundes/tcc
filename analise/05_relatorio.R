# ============================================================
# 05_relatorio.R — Export formatted tables to Word (flextable)
# ============================================================

library(tidyverse)
library(flextable)
library(officer)
library(broom)
library(broom.mixed)
library(emmeans)

df           <- readRDS("analise/df_cartoes.rds")
df_jogadores <- readRDS("analise/df_jogadores.rds")
modelos      <- readRDS("analise/modelos.rds")

dir.create("analise/resultados", showWarnings = FALSE)

df_ok  <- df           |> filter(!is.na(raca))
dfj_ok <- df_jogadores |> filter(!is.na(raca))

doc <- read_docx()

# ── Helper ─────────────────────────────────────────────────
add_table <- function(doc, ft, titulo) {
  doc <- doc |>
    body_add_par(titulo, style = "heading 2") |>
    body_add_flextable(ft) |>
    body_add_par("")
  doc
}

fmt_ft <- function(df) {
  flextable(df) |>
    theme_booktabs() |>
    autofit() |>
    fontsize(size = 10, part = "all")
}

# ── Table 1: Sample description ───────────────────────────
t1 <- df_ok |>
  count(raca, card_type) |>
  pivot_wider(names_from = card_type, values_from = n, values_fill = 0) |>
  mutate(Total = rowSums(across(where(is.numeric)))) |>
  rename(Raca = raca, Amarelo = yellow, `Amarelo-vermelho` = yellow_red, Vermelho = red)

doc <- add_table(doc, fmt_ft(t1),
                 "Tabela 1 — Distribuicao de cartoes por categoria racial")

# ── Table 2: Card rate per player by race ─────────────────
t2 <- dfj_ok |>
  group_by(raca) |>
  summarise(
    N           = n(),
    `Media amarelos`   = round(mean(n_amarelos), 2),
    `Mediana amarelos` = median(n_amarelos),
    `Media vermelhos`  = round(mean(n_vermelhos), 2),
    .groups = "drop"
  ) |>
  rename(Raca = raca)

doc <- add_table(doc, fmt_ft(t2),
                 "Tabela 2 — Estatisticas descritivas por jogador e raca")

# ── Table 3: Chi-square ────────────────────────────────────
chi <- modelos$chi_raca_tipo
t3 <- tibble(
  Estatistica = c("X²", "gl", "p-valor", "Cramer V"),
  Valor = c(
    round(chi$statistic, 3),
    chi$parameter,
    signif(chi$p.value, 3),
    round(modelos$cramer_tipo, 4)
  )
)
doc <- add_table(doc, fmt_ft(t3),
                 "Tabela 3 — Teste qui-quadrado: raca x tipo de cartao")

# ── Table 4: GLM yellow card ──────────────────────────────
t4 <- tidy(modelos$glm_amarelo, exponentiate = TRUE, conf.int = TRUE) |>
  filter(str_detect(term, "raca|Intercept")) |>
  mutate(across(where(is.numeric), ~ round(.x, 3))) |>
  rename(Termo = term, OR = estimate, `IC 2.5%` = conf.low,
         `IC 97.5%` = conf.high, `p-valor` = p.value)

doc <- add_table(doc, fmt_ft(t4),
                 "Tabela 4 — Regressao logistica: cartao amarelo")

# ── Table 5: GLM red card ─────────────────────────────────
t5 <- tidy(modelos$glm_vermelho, exponentiate = TRUE, conf.int = TRUE) |>
  filter(str_detect(term, "raca|Intercept")) |>
  mutate(across(where(is.numeric), ~ round(.x, 3))) |>
  rename(Termo = term, OR = estimate, `IC 2.5%` = conf.low,
         `IC 97.5%` = conf.high, `p-valor` = p.value)

doc <- add_table(doc, fmt_ft(t5),
                 "Tabela 5 — Regressao logistica: cartao vermelho")

# ── Table 6: GLMM fixed effects ───────────────────────────
t6 <- tidy(modelos$glmm_vermelho, exponentiate = TRUE, conf.int = TRUE,
           effects = "fixed") |>
  filter(str_detect(term, "raca|Intercept")) |>
  mutate(across(where(is.numeric), ~ round(.x, 3))) |>
  select(term, estimate, conf.low, conf.high, p.value) |>
  rename(Termo = term, OR = estimate, `IC 2.5%` = conf.low,
         `IC 97.5%` = conf.high, `p-valor` = p.value)

doc <- add_table(doc, fmt_ft(t6),
                 "Tabela 6 — GLMM (efeitos aleatorios): cartao vermelho")

# ── Table 7: Pairwise comparisons ─────────────────────────
t7 <- as.data.frame(pairs(modelos$emm_glmm, adjust = "bonferroni")) |>
  mutate(across(where(is.numeric), ~ round(.x, 4))) |>
  rename(Contraste = contrast, OR = odds.ratio, `p-valor` = p.value)

doc <- add_table(doc, fmt_ft(t7),
                 "Tabela 7 — Comparacoes pareadas (emmeans Bonferroni)")

# ── Save ──────────────────────────────────────────────────
print(doc, target = "analise/resultados/tabelas_tcc.docx")
cat("Tabelas exportadas: analise/resultados/tabelas_tcc.docx\n")
