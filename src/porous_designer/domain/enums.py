"""Domain enumerations with explicit scientific terminology."""

from enum import Enum


class DomainShape(str, Enum):
    """Bounding domain geometry."""

    BOX = "box"
    CYLINDER = "cylinder"
    SPHERE = "sphere"
    MESH = "mesh"


class OriginConvention(str, Enum):
    """Coordinate origin placement for the domain."""

    CORNER_AT_ORIGIN = "corner_at_origin"
    CENTERED = "centered"


class StructureFamily(str, Enum):
    """Supported porous structure families."""

    # Sphere-pore lattices (solid block with spherical pores)
    SC_SPHERICAL_PORES = "sc_spherical_pores"
    BCC_SPHERICAL_PORES = "bcc_spherical_pores"
    FCC_SPHERICAL_PORES = "fcc_spherical_pores"
    HCP_SPHERICAL_PORES = "hcp_spherical_pores"
    # Triply periodic minimal surfaces (sheet or network variant)
    GYROID = "gyroid"
    DIAMOND = "diamond"
    PRIMITIVE = "primitive"
    IWP = "iwp"
    NEOVIUS = "neovius"
    FISCHER_KOCH_S = "fischer_koch_s"
    LIDINOID = "lidinoid"
    # Strut (beam) lattices
    STRUT_CUBIC = "strut_cubic"
    STRUT_BCC = "strut_bcc"
    STRUT_OCTET = "strut_octet"
    STRUT_KELVIN = "strut_kelvin"
    # Stochastic open-cell foam
    VORONOI_FOAM = "voronoi_foam"

    @property
    def is_sphere_lattice(self) -> bool:
        return self in {
            StructureFamily.SC_SPHERICAL_PORES,
            StructureFamily.BCC_SPHERICAL_PORES,
            StructureFamily.FCC_SPHERICAL_PORES,
            StructureFamily.HCP_SPHERICAL_PORES,
        }

    @property
    def is_tpms(self) -> bool:
        return self in {
            StructureFamily.GYROID,
            StructureFamily.DIAMOND,
            StructureFamily.PRIMITIVE,
            StructureFamily.IWP,
            StructureFamily.NEOVIUS,
            StructureFamily.FISCHER_KOCH_S,
            StructureFamily.LIDINOID,
        }

    @property
    def is_strut_lattice(self) -> bool:
        return self in {
            StructureFamily.STRUT_CUBIC,
            StructureFamily.STRUT_BCC,
            StructureFamily.STRUT_OCTET,
            StructureFamily.STRUT_KELVIN,
        }

    @property
    def is_stochastic(self) -> bool:
        return self == StructureFamily.VORONOI_FOAM

    @property
    def uses_unit_cell(self) -> bool:
        """Families sized by a unit-cell (or mean cell) size rather than a pore diameter."""
        return not self.is_sphere_lattice

    @property
    def supports_step(self) -> bool:
        """Faceted STEP is produced best-effort for every family (size-limited)."""
        return True

    @property
    def legacy_lattice_key(self) -> str | None:
        """Map to porousgen.py lattice key for migration."""
        mapping = {
            StructureFamily.SC_SPHERICAL_PORES: "sc",
            StructureFamily.BCC_SPHERICAL_PORES: "bcc",
            StructureFamily.FCC_SPHERICAL_PORES: "fcc",
            StructureFamily.HCP_SPHERICAL_PORES: "hcp",
            StructureFamily.GYROID: "gyroid",
        }
        return mapping.get(self)


class TPMSVariant(str, Enum):
    """Sheet: solid shell of given thickness around the surface. Network: solid on one side."""

    SHEET = "sheet"
    NETWORK = "network"


class GradingMode(str, Enum):
    LINEAR = "linear"
    RADIAL = "radial"
    SURFACE_DISTANCE = "surface_distance"


class SkinMode(str, Enum):
    ALL = "all"
    LATERAL = "lateral"


class ExportFormat(str, Enum):
    STL = "stl"
    STEP = "step"
    THREE_MF = "3mf"
    NPZ = "npz"
    YAML = "yaml"
    JSON = "json"
    HTML = "html"
    PNG = "png"


class RunStatus(str, Enum):
    """Blackboard lifecycle states."""

    CREATED = "created"
    REQUEST_ENTERED = "request_entered"
    REQUEST_PARSED = "request_parsed"
    AMBIGUITY_REVIEW_REQUIRED = "ambiguity_review_required"
    SPECIFICATION_PROPOSED = "specification_proposed"
    SPECIFICATION_REVIEWED = "specification_reviewed"
    SPECIFICATION_APPROVED = "specification_approved"
    SPECIFICATION_REJECTED = "specification_rejected"
    PARSING = "parsing"
    NEEDS_USER_REVIEW = "needs_user_review"
    FEASIBILITY_CHECKING = "feasibility_checking"
    INFEASIBLE = "infeasible"
    PREVIEW_GENERATING = "preview_generating"
    PREVIEW_READY = "preview_ready"
    FINAL_GENERATING = "final_generating"
    VALIDATING = "validating"
    REPAIRING = "repairing"
    PASSED = "passed"
    FAILED = "failed"
    EXPORTED = "exported"
    CANCELLED = "cancelled"


class ValidationStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NOT_MEASURED = "not_measured"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class FeasibilityStatus(str, Enum):
    FEASIBLE = "feasible"
    CONDITIONALLY_FEASIBLE = "conditionally_feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"


class ErrorCode(str, Enum):
    SPEC_AMBIGUOUS = "spec_ambiguous"
    SPEC_INVALID = "spec_invalid"
    SPEC_INFEASIBLE = "spec_infeasible"
    MEMORY_ESTIMATE_EXCEEDED = "memory_estimate_exceeded"
    POROSITY_TARGET_UNREACHABLE = "porosity_target_unreachable"
    GEOMETRY_EMPTY = "geometry_empty"
    GEOMETRY_DISCONNECTED = "geometry_disconnected"
    MESH_NOT_WATERTIGHT = "mesh_not_watertight"
    WALL_THICKNESS_VIOLATION = "wall_thickness_violation"
    THROAT_SIZE_VIOLATION = "throat_size_violation"
    PORE_CONNECTIVITY_FAILURE = "pore_connectivity_failure"
    STEP_BOOLEAN_FAILURE = "step_boolean_failure"
    STEP_VALIDATION_FAILURE = "step_validation_failure"
    EXPORT_FAILURE = "export_failure"
    LLM_SCHEMA_FAILURE = "llm_schema_failure"
    USER_CANCELLED = "user_cancelled"


class LLMMode(str, Enum):
    STRUCTURED_ONLY = "structured_only"
    ASSISTED = "assisted"
