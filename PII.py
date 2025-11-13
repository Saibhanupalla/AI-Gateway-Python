import json
import os
from typing import Dict, Tuple
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

class PIIMapper:
    def __init__(self, mapping_file: str = "pii_mapping.json"):
        self.mapping_file = mapping_file
        self.original_to_masked: Dict[str, str] = {}
        self.masked_to_original: Dict[str, str] = {}
        self.load_mappings()
    
    def load_mappings(self):
        """Load existing mappings from file if it exists"""
        if os.path.exists(self.mapping_file):
            try:
                with open(self.mapping_file, 'r') as f:
                    mappings = json.load(f)
                    self.original_to_masked = mappings.get('forward', {})
                    self.masked_to_original = mappings.get('reverse', {})
            except (json.JSONDecodeError, IOError):
                print(f"Warning: Could not load mappings from {self.mapping_file}")
    
    def save_mappings(self):
        """Save current mappings to file"""
        try:
            with open(self.mapping_file, 'w') as f:
                json.dump({
                    'forward': self.original_to_masked,
                    'reverse': self.masked_to_original
                }, f, indent=2)
        except IOError:
            print(f"Warning: Could not save mappings to {self.mapping_file}")
    
    def add_mapping(self, original: str, masked: str):
        """Add a new mapping between original and masked values"""
        self.original_to_masked[original] = masked
        self.masked_to_original[masked] = original
        self.save_mappings()
    
    def get_masked_value(self, original: str) -> str | None:
        """Get existing masked value or None"""
        return self.original_to_masked.get(original)
    
    def get_original_value(self, masked: str) -> str | None:
        """Get original value from masked value or None"""
        return self.masked_to_original.get(masked)

# Global mapper instance
_mapper = PIIMapper()

def anonymize_text(text: str, preserve_mapping: bool = True) -> Tuple[str, Dict[str, str]]:
    """
    Anonymize text containing PII and optionally maintain mapping of original to masked values.
    
    Args:
        text: Input text to anonymize
        preserve_mapping: Whether to save mapping between original and masked values
    
    Returns:
        Tuple of (anonymized text, dictionary of detected PII entities)
    """
    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()

    # Expanded entity list for better coverage
    entity_list = [
        'SSN', 'PERSON', 'EMAIL', 'PHONE_NUMBER',
        'EMAIL_ADDRESS', 'NAME', 'CREDIT_CARD', 'IP_ADDRESS',
        'DATE_TIME', 'LOCATION', 'URL'
    ]
    results = analyzer.analyze(text=text, entities=entity_list, language='en')


    # Build operators dict for custom masking
    operators = {}
    # Improved mapping: {(entity_type, original): masked}
    detected_pii = {}
    from presidio_anonymizer.entities import RecognizerResult as AnonymizerRecognizerResult
    converted_results = []
    entity_spans = []  # Track spans for later mapping
    for result in results:
        original_value = text[result.start:result.end]
        entity_type = result.entity_type
        existing_mask = _mapper.get_masked_value(original_value)
        if existing_mask:
            operators[entity_type] = OperatorConfig("custom", {"lambda": (lambda x, mask=existing_mask: str(mask))})
        # Track entity type, original, and span
        entity_spans.append((entity_type, original_value, result.start, result.end))
        # Convert to anonymizer RecognizerResult
        converted_results.append(
            AnonymizerRecognizerResult(
                entity_type=entity_type,
                start=result.start,
                end=result.end,
                score=result.score
            )
        )

    # Anonymize the detected PII entities
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=converted_results,
        operators=operators if operators else None
    )

    # Update mappings with new masked values
    if preserve_mapping:
        for (entity_type, original_value, start, end) in entity_spans:
            masked_value = anonymized.text[start:end]
            detected_pii[(entity_type, original_value)] = masked_value
            if original_value != masked_value:
                _mapper.add_mapping(original_value, masked_value)

    return anonymized.text, detected_pii

    # Anonymize the detected PII entities
    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=converted_results,
        operators=operators if operators else None
    )

    # Update mappings with new masked values
    if preserve_mapping:
        for result in results:
            original_value = text[result.start:result.end]
            masked_value = anonymized.text[result.start:result.end]
            detected_pii[original_value] = masked_value
            if original_value != masked_value:
                _mapper.add_mapping(original_value, masked_value)

    return anonymized.text, detected_pii
