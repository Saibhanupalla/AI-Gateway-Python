from PII import anonymize_text

edge_cases = [
    # Multiple PII entities
    "Contact John Doe at john.doe@example.com or call 555-123-4567. His SSN is 123-45-6789.",
    # Overlapping entities (name inside email)
    "Jane Smith's email is jane.smith@company.com and her phone is (123) 456-7890.",
    # Non-English input (Spanish)
    "Mi nombre es Juan Pérez y mi correo es juan.perez@ejemplo.com.",
    # Non-English input (French)
    "Mon numéro de téléphone est 06 12 34 56 78 et mon email est pierre.dupont@exemple.fr.",
    # Edge: ambiguous number
    "My lucky number is 123-45-6789 but it's not my SSN.",
    # Edge: no PII
    "The quick brown fox jumps over the lazy dog.",
]

for i, text in enumerate(edge_cases, 1):
    masked, mapping = anonymize_text(text)
    print(f"\nTest Case {i}:")
    print(f"Original: {text}")
    print(f"Masked:   {masked}")
    print(f"Mapping:  {mapping}")
    # Add your own expected/actual review here
