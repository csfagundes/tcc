# ============================================================
# 04_visualizacoes.R — 9 publication-quality figures (300 dpi)
# ============================================================

library(tidyverse)
library(lme4)
library(emmeans)
library(patchwork)
library(scales)

df           <- readRDS("analise/df_cartoes.rds")
df_jogadores <- readRDS("analise/df_jogadores.rds")
modelos      <- readRDS("analise/modelos.rds")

dir.create("analise/figuras", showWarnings = FALSE)

df_ok  <- df           |> filter(!is.na(raca))
dfj_ok <- df_jogadores |> filter(!is.na(raca))

cores_raca <- c(Branco = "#4E79A7", Pardo = "#F28E2B", Preto = "#59A14F")

tema_tcc <- theme_minimal(base_size = 13) +
  theme(
    plot.title    = element_text(face = "bold"),
    plot.subtitle = element_text(color = "grey40"),
    legend.position = "bottom",
    panel.grid.minor = element_blank()
  )

salvar <- function(nome, p, w = 8, h = 5) {
  ggsave(file.path("analise/figuras", paste0(nome, ".png")),
         plot = p, width = w, height = h, dpi = 300, bg = "white")
  cat("Salvo:", nome, "\n")
}

# ── Fig 1: Card distribution by race ──────────────────────
p1 <- df_ok |>
  count(raca, card_type) |>
  ggplot(aes(x = raca, y = n, fill = card_type)) +
  geom_col(position = "dodge") +
  scale_fill_manual(
    values = c(yellow = "#F5C518", yellow_red = "#E87722", red = "#C0392B"),
    labels = c("Amarelo", "Amarelo-vermelho", "Vermelho"),
    name   = "Tipo"
  ) +
  labs(title = "Figura 1 — Distribuicao de cartoes por raca",
       x = "Raca", y = "N de cartoes") +
  tema_tcc
salvar("fig1_cartoes_por_raca", p1)

# ── Fig 2: Red card rate by race ───────────────────────────
p2 <- df_ok |>
  group_by(raca) |>
  summarise(
    taxa = mean(cartao_vermelho),
    se   = sqrt(taxa * (1 - taxa) / n()),
    .groups = "drop"
  ) |>
  ggplot(aes(x = raca, y = taxa, fill = raca)) +
  geom_col(width = 0.6) +
  geom_errorbar(aes(ymin = taxa - 1.96 * se, ymax = taxa + 1.96 * se),
                width = 0.2) +
  scale_fill_manual(values = cores_raca, guide = "none") +
  scale_y_continuous(labels = percent_format(accuracy = 0.1)) +
  labs(title = "Figura 2 — Taxa de cartao vermelho por raca",
       subtitle = "Media +/- IC 95%",
       x = "Raca", y = "Proporcao de cartoes vermelhos") +
  tema_tcc
salvar("fig2_taxa_vermelho_raca", p2)

# ── Fig 3: Cards by season and race ───────────────────────
p3 <- df_ok |>
  count(season, raca) |>
  ggplot(aes(x = season, y = n, color = raca, group = raca)) +
  geom_line(linewidth = 1) +
  geom_point(size = 2.5) +
  scale_color_manual(values = cores_raca, name = "Raca") +
  labs(title = "Figura 3 — Cartoes por temporada e raca",
       x = "Temporada", y = "N de cartoes") +
  tema_tcc
salvar("fig3_cartoes_temporada", p3)

# ── Fig 4: Cards per player distribution (violin) ─────────
p4 <- dfj_ok |>
  ggplot(aes(x = raca, y = n_total, fill = raca)) +
  geom_violin(alpha = 0.7, trim = TRUE) +
  geom_boxplot(width = 0.1, outlier.shape = NA) +
  scale_fill_manual(values = cores_raca, guide = "none") +
  labs(title = "Figura 4 — Cartoes totais por jogador (2018-2023)",
       x = "Raca", y = "Total de cartoes por jogador") +
  tema_tcc
salvar("fig4_violin_cartoes_jogador", p4)

# ── Fig 5: Home vs Away by race ───────────────────────────
p5 <- df_ok |>
  group_by(raca, home_away) |>
  summarise(taxa_vm = mean(cartao_vermelho), .groups = "drop") |>
  ggplot(aes(x = raca, y = taxa_vm, fill = home_away)) +
  geom_col(position = "dodge", width = 0.6) +
  scale_fill_manual(values = c(home = "#2196F3", away = "#FF5722"),
                    labels = c("Casa", "Fora"), name = "") +
  scale_y_continuous(labels = percent_format(accuracy = 0.1)) +
  labs(title = "Figura 5 — Taxa de cartao vermelho: casa vs fora por raca",
       x = "Raca", y = "Proporcao de cartoes vermelhos") +
  tema_tcc
salvar("fig5_home_away_raca", p5)

# ── Fig 6: OR forest plot (GLM vermelho) ──────────────────
library(broom)
coef_glm <- tidy(modelos$glm_vermelho, exponentiate = TRUE, conf.int = TRUE) |>
  filter(str_detect(term, "raca"))

p6 <- coef_glm |>
  mutate(term = str_remove(term, "raca")) |>
  ggplot(aes(x = estimate, y = term, xmin = conf.low, xmax = conf.high)) +
  geom_pointrange() +
  geom_vline(xintercept = 1, linetype = "dashed", color = "grey50") +
  labs(title = "Figura 6 — Odds Ratio: raca (ref = Branco)",
       subtitle = "Regressao logistica — cartao vermelho",
       x = "Odds Ratio (IC 95%)", y = "") +
  tema_tcc
salvar("fig6_forest_glm_vermelho", p6)

# ── Fig 7: OR forest plot (GLMM) ──────────────────────────
library(broom.mixed)
coef_glmm <- tidy(modelos$glmm_vermelho, exponentiate = TRUE, conf.int = TRUE,
                  effects = "fixed") |>
  filter(str_detect(term, "raca"))

p7 <- coef_glmm |>
  mutate(term = str_remove(term, "raca")) |>
  ggplot(aes(x = estimate, y = term, xmin = conf.low, xmax = conf.high)) +
  geom_pointrange() +
  geom_vline(xintercept = 1, linetype = "dashed", color = "grey50") +
  labs(title = "Figura 7 — Odds Ratio: raca (ref = Branco)",
       subtitle = "GLMM com efeitos aleatorios (clube e temporada)",
       x = "Odds Ratio (IC 95%)", y = "") +
  tema_tcc
salvar("fig7_forest_glmm_vermelho", p7)

# ── Fig 8: EMMs pairwise (GLMM) ───────────────────────────
emm_df <- as.data.frame(modelos$emm_glmm)

p8 <- emm_df |>
  ggplot(aes(x = raca, y = prob, ymin = asymp.LCL, ymax = asymp.UCL,
             color = raca)) +
  geom_pointrange(size = 1) +
  scale_color_manual(values = cores_raca, guide = "none") +
  scale_y_continuous(labels = percent_format(accuracy = 0.1)) +
  labs(title = "Figura 8 — Probabilidade estimada de cartao vermelho (GLMM)",
       subtitle = "Marginal means +/- IC 95%",
       x = "Raca", y = "P(cartao vermelho)") +
  tema_tcc
salvar("fig8_emm_glmm", p8)

# ── Fig 9: Cards by position and race (stacked %) ─────────
p9 <- df_ok |>
  filter(!is.na(position)) |>
  count(position, raca) |>
  group_by(position) |>
  mutate(pct = n / sum(n)) |>
  ggplot(aes(x = position, y = pct, fill = raca)) +
  geom_col(width = 0.7) +
  scale_fill_manual(values = cores_raca, name = "Raca") +
  scale_y_continuous(labels = percent_format()) +
  labs(title = "Figura 9 — Composicao racial dos cartoes por posicao",
       x = "Posicao", y = "Proporcao") +
  tema_tcc
salvar("fig9_posicao_raca_stack", p9)

cat("\nTodas as figuras salvas em analise/figuras/\n")
