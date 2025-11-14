def compute_price(exam, pack_type, subject_code=None):
    level = exam.level
    name = exam.name
    is_long = exam.is_long_model

    # Cas 1 : Examens à 3 packs
    exams_with_three_packs = ["BAC C", "BAC D", "BAC F4", "DTI/STI", "CAP/CB", "BEPC (modèle court)"]

    if name in exams_with_three_packs:
        if pack_type == 'DOUBLE':
            if level in ('BAC', 'DTI/STI'):
                return 2500
            if level in ('CAP/CB', 'BEPC') and not is_long:
                return 1500
            return 0
        else:  # pack MATH ou PCT
            if level in ('BAC', 'DTI/STI'):
                return 1500
            if level in ('CAP/CB', 'BEPC') and not is_long:
                return 1000
            return 0

    # Cas 2 : Examens à 1 seul pack (Math uniquement)
    exams_with_one_pack = ["BAC A1", "BAC A2", "BAC B", "BAC G2", "BEPC (modèle long)"]

    if name in exams_with_one_pack:
        if pack_type == 'MATH':
            return 1000
        return 0

    # Par défaut, aucun prix
    return 0
