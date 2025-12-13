"""
Constants for product application.
All magic numbers and strings should be defined here.
"""


class TariffConstants:
    """Constants related to tariffs"""
    NO_INSTALLMENT_KEYWORD = "No installment"


class ApplicationStages:
    """Application stages from Grist"""
    NEW = 'New'
    ASSESSMENT = 'Assessment'
    ACCEPTED = 'Accepted'
    DENIED = 'Denied'
    DENIED_BY_CLIENT = 'Denied by client'
    SUCCESS = 'Success'
    
    # Final stages that require special handling
    FINAL_STAGES = [ACCEPTED, DENIED, DENIED_BY_CLIENT, SUCCESS]
    
    # Stages that allow new applications
    ALLOW_NEW_APPLICATION_STAGES = [SUCCESS, DENIED_BY_CLIENT]
    
    # Stages that block new applications
    BLOCK_NEW_APPLICATION_STAGES = [ACCEPTED, ASSESSMENT, NEW]


class TimeConstants:
    """Time-related constants"""
    DENIED_COOLDOWN_DAYS = 30  # Days to wait after denial before allowing new application


class SIMKeywords:
    """Keywords for SIM matching"""
    SIM_KEYWORDS = ["SIM", "DUAL", "ESIM"]
    
    @classmethod
    def has_sim_info(cls, text):
        """Check if text contains SIM-related keywords"""
        text_upper = text.upper()
        return any(keyword in text_upper for keyword in cls.SIM_KEYWORDS)


class CalculationModes:
    """Calculation mode constants"""
    MODE_1 = 1  # Common advance payment and tariff for all products
    MODE_2 = 2  # Individual advance payment and tariff for each product
    
    VALID_MODES = [MODE_1, MODE_2]

