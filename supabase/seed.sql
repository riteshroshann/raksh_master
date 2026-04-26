INSERT INTO reference_ranges (parameter_name, sex, age_min, age_max, range_low, range_high, unit, source, source_citation, population)
VALUES
    ('hemoglobin', 'female', NULL, NULL, 11.5, 15.0, 'g/dL', 'ICMR', 'ICMR Reference Intervals for Indian Population, 2023', 'indian'),
    ('hemoglobin', 'male', NULL, NULL, 13.0, 17.0, 'g/dL', 'ICMR', 'ICMR Reference Intervals for Indian Population, 2023', 'indian'),
    ('tsh', 'any', 18, 59, 0.4, 5.5, 'mIU/L', 'ICMR', 'ICMR Thyroid Reference Study, Indian Cohort', 'indian'),
    ('tsh', 'male', 60, NULL, 0.4, 6.08, 'mIU/L', 'ICMR', 'ICMR Elderly Thyroid Reference Study', 'indian'),
    ('tsh', 'female', 60, NULL, 0.4, 6.37, 'mIU/L', 'ICMR', 'ICMR Elderly Thyroid Reference Study', 'indian'),
    ('platelets', 'any', NULL, NULL, 115600, 400000, '/uL', 'ICMR', 'ICMR Hematology Reference Intervals, Indian Population', 'indian'),
    ('hdl', 'male', NULL, NULL, 35, 65, 'mg/dL', 'RSSDI', 'RSSDI Lipid Guidelines for Indian Population', 'indian'),
    ('hdl', 'female', NULL, NULL, 40, 75, 'mg/dL', 'RSSDI', 'RSSDI Lipid Guidelines for Indian Population', 'indian'),
    ('ldl', 'any', NULL, NULL, 0, 100, 'mg/dL', 'RSSDI', 'RSSDI Lipid Guidelines for Indian Population', 'indian'),
    ('fasting_glucose', 'any', NULL, NULL, 70, 100, 'mg/dL', 'RSSDI', 'RSSDI Diabetes Management Guidelines', 'indian'),
    ('hba1c', 'any', NULL, NULL, 4.0, 5.6, '%', 'RSSDI', 'RSSDI Diabetes Management Guidelines', 'indian'),
    ('creatinine', 'male', NULL, NULL, 0.7, 1.3, 'mg/dL', 'ICMR', 'ICMR Renal Reference Intervals', 'indian'),
    ('creatinine', 'female', NULL, NULL, 0.6, 1.1, 'mg/dL', 'ICMR', 'ICMR Renal Reference Intervals', 'indian'),
    ('total_cholesterol', 'any', NULL, NULL, 0, 200, 'mg/dL', 'RSSDI', 'RSSDI Lipid Guidelines for Indian Population', 'indian'),
    ('triglycerides', 'any', NULL, NULL, 0, 150, 'mg/dL', 'RSSDI', 'RSSDI Lipid Guidelines for Indian Population', 'indian');
