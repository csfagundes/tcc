# ============================================================
# 00_setup.R — Install packages and define shared theme/palette
# ============================================================

pkgs <- c(
  "tidyverse", "readxl", "janitor", "lme4", "MASS",
  "emmeans", "vcd", "car", "flextable", "officer",
  "scales", "patchwork", "broom", "broom.mixed"
)

to_install <- pkgs[!pkgs %in% installed.packages()[, "Package"]]
if (length(to_install) > 0) {
  install.packages(to_install, dependencies = TRUE)
}

# Shared ggplot2 theme
library(ggplot2)
tema_tcc <- theme_minimal(base_size = 13) +
  theme(
    plot.title    = element_text(face = "bold", size = 14),
    plot.subtitle = element_text(color = "grey40"),
    legend.position = "bottom",
    panel.grid.minor = element_blank()
  )

# IBGE-inspired palette
cores_raca <- c(
  Branco = "#4E79A7",
  Pardo  = "#F28E2B",
  Preto  = "#59A14F"
)

cat("Setup OK.\n")
