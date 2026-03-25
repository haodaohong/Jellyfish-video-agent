from __future__ import annotations

from enum import Enum


class ProjectStyle(str, Enum):
    """项目题材/风格维度（不用于区分真人/动漫）。"""

    realism = "现实主义"
    scifi = "科幻"
    ancient = "古风"
    urban_comedy = "都市喜剧"


class ProjectVisualStyle(str, Enum):
    """画面表现形式维度：用于区分真人/动漫等。"""

    live_action = "真人"
    anime = "动漫"


class ChapterStatus(str, Enum):
    """章节生产状态。"""

    draft = "draft"
    shooting = "shooting"
    done = "done"


class ShotStatus(str, Enum):
    """镜头生成状态（更多是“生产流程”而非剧情状态）。"""

    pending = "pending"
    generating = "generating"
    ready = "ready"


class CameraShotType(str, Enum):
    """景别（与 `app.schemas.skills.common.ShotType` 对齐，存英文 code）。"""

    ecu = "ECU"  # 大特写
    cu = "CU"  # 特写
    mcu = "MCU"  # 中近景
    ms = "MS"  # 中景
    mls = "MLS"  # 中远景
    ls = "LS"  # 远景
    els = "ELS"  # 大远景


class CameraAngle(str, Enum):
    """机位角度（与 `app.schemas.skills.common.CameraAngle` 对齐，存英文 code）。"""

    eye_level = "EYE_LEVEL"  # 平视
    high_angle = "HIGH_ANGLE"  # 高角度
    low_angle = "LOW_ANGLE"  # 低角度
    bird_eye = "BIRD_EYE"  # 鸟瞰
    dutch = "DUTCH"  # 荷兰式
    over_shoulder = "OVER_SHOULDER"  # 过肩


class CameraMovement(str, Enum):
    """运镜方式（与 `app.schemas.skills.common.CameraMovement` 对齐，存英文 code）。"""

    static = "STATIC"  # 静止
    pan = "PAN"  # 平移
    tilt = "TILT"  # 倾斜
    dolly_in = "DOLLY_IN"  # 拉近
    dolly_out = "DOLLY_OUT"  # 拉远
    track = "TRACK"  # 轨道
    crane = "CRANE"  # 摇臂
    handheld = "HANDHELD"  # 手持
    steadicam = "STEADICAM"  # 稳定器
    zoom_in = "ZOOM_IN"
    zoom_out = "ZOOM_OUT"  # 拉近


class AssetQualityLevel(str, Enum):
    """资产精度等级（由低到高逐步补齐更多角度/细节图）。"""

    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    ultra = "ULTRA"


class AssetViewAngle(str, Enum):
    """资产图片角度（用于多视图描述同一资产）。"""

    front = "FRONT"
    left = "LEFT"
    right = "RIGHT"
    back = "BACK"
    three_quarter = "THREE_QUARTER"
    top = "TOP"
    detail = "DETAIL"


class ShotFrameType(str, Enum):
    """镜头分镜帧类型：首帧/尾帧/关键帧。"""

    first = "first"
    last = "last"
    key = "key"


class FileType(str, Enum):
    """文件类型（用于素材库与时间线引用）。"""

    image = "image"
    video = "video"


class TimelineClipType(str, Enum):
    """时间线片段类型（视频/音频）。"""

    video = "video"
    audio = "audio"


class DialogueLineMode(str, Enum):
    """对白模式（与 `app.schemas.skills.common.DialogueLineMode` 对齐，存英文 code）。"""

    dialogue = "DIALOGUE"  # 对白
    voice_over = "VOICE_OVER"  # 旁白
    off_screen = "OFF_SCREEN"  # 画外音
    phone = "PHONE"  # 电话声


class VFXType(str, Enum):
    """视效类型（与 `app.schemas.skills.common.VFXType` 对齐，存英文 code）。"""

    none = "NONE"  # 无
    particles = "PARTICLES"  # 粒子
    volumetric_fog = "VOLUMETRIC_FOG"  # 体积雾
    cg_double = "CG_DOUBLE"  # 数字替身
    digital_environment = "DIGITAL_ENVIRONMENT"  # 数字场景
    matte_painting = "MATTE_PAINTING"  # 绘景
    fire_smoke = "FIRE_SMOKE"  # 烟火
    water_sim = "WATER_SIM"  # 水效
    destruction = "DESTRUCTION"  # 破碎/解算
    energy_magic = "ENERGY_MAGIC"  # 能量/魔法
    compositing_cleanup = "COMPOSITING_CLEANUP"  # 合成/修脏
    slow_motion_time = "SLOW_MOTION_TIME"  # 升格/慢动作
    other = "OTHER"  # 其他


class ImportDraftType(str, Enum):
    """导入草稿类型（用于 occurrence 归档）。"""

    character = "character"
    scene = "scene"
    prop = "prop"
    costume = "costume"


class PromptCategory(str, Enum):
    """提示词模板类别。"""

    frame_head = "frame_head"
    frame_tail = "frame_tail"
    frame_key = "frame_key"
    video = "video"
    storyboard = "storyboard"
    bgm = "bgm"
    sfx = "sfx"
    character_front = "character_front"
    character_other = "character_other"
    actor_image_front = "actor_image_front"
    actor_image_other = "actor_image_other"
    prop_front = "prop_front"
    prop_other = "prop_other"
    scene_front = "scene_front"
    scene_other = "scene_other"
    costume_front = "costume_front"
    costume_other = "costume_other"
    combined = "combined"

