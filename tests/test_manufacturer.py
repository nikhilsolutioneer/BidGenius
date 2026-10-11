from tenderproof.matching import infer_attributes


def test_actual_tender_example_manufacturer_syntax_and_blank_placeholder():
    assert infer_attributes("Fabrikat z.B. Trox Hesco AG\nTyp TVR")['manufacturer'] == 'Trox Hesco AG'
    assert infer_attributes("Fabrikat: z.B. Ventaflex GmbH\nTyp VFL")['manufacturer'] == 'Ventaflex GmbH'
    assert infer_attributes("Fabrikat z.B.Troxhesco")['manufacturer'] == 'Troxhesco'
    assert 'manufacturer' not in infer_attributes("Fabrikat: ..................\nTyp")
