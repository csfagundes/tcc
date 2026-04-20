# ============================================================
# rodar_tudo.R — Execute full analysis pipeline in order
# Run from the tcc/ root directory:
#   Rscript analise/rodar_tudo.R
# ============================================================

setwd(dirname(rstudioapi::getSourceEditorContext()$path) |>
        dirname() |>
        normalizePath())

cat("Working directory:", getwd(), "\n\n")

scripts <- c(
  "analise/00_setup.R",
  "analise/01_carregar_dados.R",
  "analise/02_descritiva.R",
  "analise/03_inferencial.R",
  "analise/04_visualizacoes.R",
  "analise/05_relatorio.R"
)

for (s in scripts) {
  cat(rep("=", 60), "\n", sep = "")
  cat(">>> Rodando:", s, "\n")
  cat(rep("=", 60), "\n", sep = "")
  source(s, echo = FALSE)
  cat("\n")
}

cat("Pipeline completo.\n")
cat("Resultados em: analise/figuras/ e analise/resultados/\n")
