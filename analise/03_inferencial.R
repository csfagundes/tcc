# ============================================================
# 03_inferencial.R — Chi-square, logistic regression, GLMM,
#                    negative binomial, emmeans comparisons
# ============================================================

library(tidyverse)
library(lme4)
library(MASS)
library(emmeans)
library(vcd)
library(car)
library(broom)
library(broom.mixed)

df           <- readRDS("analise/df_cartoes.rds")
df_jogadores <- readRDS("analise/df_jogadores.rds")

# Keep only rows with valid race classification
df_ok  <- df           |> filter(!is.na(raca))
dfj_ok <- df_jogadores |> filter(!is.na(raca))

# ── 1. Chi-square: race × card type ───────────────────────
cat("\n=== 1. Chi-square: raca x tipo de cartao ===\n")
tab_chi <- table(df_ok$raca, df_ok$card_type)
print(tab_chi)
chi_res <- chisq.test(tab_chi)
print(chi_res)

# Cramér's V
V <- assocstats(tab_chi)$cramer
cat(sprintf("Cramer V = %.4f\n", V))

# ── 2. Chi-square: race × red card (binary) ───────────────
cat("\n=== 2. Chi-square: raca x cartao vermelho ===\n")
tab_vm <- table(df_ok$raca, df_ok$cartao_vermelho)
print(chisq.test(tab_vm))
cat(sprintf("Cramer V = %.4f\n", assocstats(tab_vm)$cramer))

# ── 3. Logistic regression — yellow card ──────────────────
cat("\n=== 3. GLM — cartao amarelo (binario) ===\n")
df_ok <- df_ok |>
  mutate(amarelo = as.integer(card_type == "yellow"))

glm_amarelo <- glm(
  amarelo ~ raca + position + home_away + season,
  data   = df_ok,
  family = binomial(link = "logit")
)
print(tidy(glm_amarelo, exponentiate = TRUE, conf.int = TRUE))
cat("\nVIF:\n"); print(vif(glm_amarelo))

# ── 4. Logistic regression — red card ─────────────────────
cat("\n=== 4. GLM — cartao vermelho (binario) ===\n")
glm_vermelho <- glm(
  cartao_vermelho ~ raca + position + home_away + season,
  data   = df_ok,
  family = binomial(link = "logit")
)
print(tidy(glm_vermelho, exponentiate = TRUE, conf.int = TRUE))

# ── 5. GLMM — random effects by club and season ───────────
cat("\n=== 5. GLMM — cartao vermelho (random: club + season) ===\n")
glmm_vm <- glmer(
  cartao_vermelho ~ raca + position + home_away + (1 | club) + (1 | season),
  data   = df_ok,
  family = binomial(link = "logit"),
  control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 2e5))
)
print(summary(glmm_vm))
print(tidy(glmm_vm, exponentiate = TRUE, conf.int = TRUE))

# ── 6. Negative binomial — card count per player ──────────
cat("\n=== 6. Negative binomial — total de cartoes por jogador ===\n")
nb_model <- glm.nb(
  n_total ~ raca + position,
  data = dfj_ok
)
print(tidy(nb_model, exponentiate = TRUE, conf.int = TRUE))

# ── 7. Pairwise comparisons (emmeans, Bonferroni) ─────────
cat("\n=== 7. Emmeans pairwise — GLM vermelho ===\n")
emm <- emmeans(glm_vermelho, ~ raca, type = "response")
print(pairs(emm, adjust = "bonferroni"))

cat("\n=== 7b. Emmeans pairwise — GLMM vermelho ===\n")
emm_glmm <- emmeans(glmm_vm, ~ raca, type = "response")
print(pairs(emm_glmm, adjust = "bonferroni"))

# ── Save models ───────────────────────────────────────────
saveRDS(list(
  chi_raca_tipo    = chi_res,
  cramer_tipo      = V,
  glm_amarelo      = glm_amarelo,
  glm_vermelho     = glm_vermelho,
  glmm_vermelho    = glmm_vm,
  nb_jogador       = nb_model,
  emm_glm          = emm,
  emm_glmm         = emm_glmm
), "analise/modelos.rds")

cat("\nAnalise inferencial concluida.\n")
