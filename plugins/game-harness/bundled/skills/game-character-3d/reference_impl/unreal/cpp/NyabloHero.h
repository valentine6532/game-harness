#pragma once

#include "CoreMinimal.h"
#include "NyabloCharacter.h"
#include "NyabloHero.generated.h"

class UAnimSequence;
class USkeletalMesh;
class USkeletalMeshComponent;
class UCameraComponent;
class UWindDirectionalSourceComponent;
class UNiagaraSystem;
class UInputAction;
class UInputMappingContext;
class USpringArmComponent;
struct FInputActionValue;

/**
 * Player cat: WASD moves relative to the fixed quarter-view camera, LMB / Space / J attacks
 * (turning toward the mouse cursor on the ground). Input actions are created in code.
 * Command line -NyabloAuto drives the hero, takes screenshots and quits (automated check).
 */
/** One swing of the hero's combo: plays [StartFraction, EndFraction] of Anim, hits at HitFraction. */
USTRUCT(BlueprintType)
struct FNyabloAttackClip
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	TObjectPtr<UAnimSequence> Anim;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float StartFraction = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float HitFraction = 0.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float EndFraction = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float PlayRate = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float DamageScale = 1.f;

	/** Time warp (4-28): before StrikeFraction (the hand's speed-up) the clip plays at WindupRate, from there to the
	 *  hit at StrikeRate, after the hit at PlayRate. Slower wind-up reads, the snap stays a snap. < 0 = PlayRate throughout. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float StrikeFraction = -1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float WindupRate = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float StrikeRate = 1.f;

	/** Load at the top (10-01): the last ApexFrames clip frames before StrikeFraction play at ApexRate, so the swing
	 *  settles before the snap instead of flowing through at one speed. ApexFrames <= 0 = off. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float ApexFrames = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float ApexRate = 1.f;

	/** Impact (4-33): after the hit the blade snaps FollowFrames clip frames on at FollowRate (<= 0: StrikeRate), the
	 *  extended pose holds HoldSeconds, then the rest recovers at RecoverRate (<= 0: PlayRate). FollowFrames <= 0 = off
	 *  (after the hit at PlayRate). Mocap swings otherwise drift on after contact and read as sweeping the air. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float FollowFrames = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float FollowRate = -1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float HoldSeconds = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	float RecoverRate = -1.f;

	/** Body travel over the window (cm, actor space: X forward, Y right). The clip's hip carries it during the swing
	 *  (re-zeroed at the window start); the capsule catches up by this much when the swing ends (4-27). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo")
	FVector Lunge = FVector::ZeroVector;
};

UCLASS()
class NYABLO_API ANyabloHero : public ANyabloCharacter
{
	GENERATED_BODY()

public:
	ANyabloHero();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Camera")
	float CameraPitch = -40.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Camera")
	float CameraYaw = -97.4f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Camera")
	float CameraDistance = 2100.f;

	/** Mouse wheel zoom range (cm) and step per wheel notch. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Camera")
	float CameraMinDistance = 1400.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Camera")
	float CameraMaxDistance = 2400.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Camera")
	float CameraZoomStep = 150.f;

	/** Basic attack combo (Mixamo clips); empty = the single AttackAnim segment. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combo")
	TArray<FNyabloAttackClip> ComboAttacks;

	/** Next attack continues the combo if it starts within this many seconds of the previous swing ending. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combo")
	float ComboResetSeconds = 0.6f;

	/** Combo clip used for the shockwave slam (-1 = AttackAnim). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combo")
	int32 SkillClipIndex = -1;

	/** Cape wind (4-15): the hero carries a directional wind source for its Chaos cloth. Running blows against the
	 *  movement (cape trails), every swing adds a short gust from the front (cape flaps off the back). m/s. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Cape")
	float CapeTrailWind = 10.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Cape")
	float CapeGustWind = 26.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Cape")
	float CapeGustSeconds = 0.6f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Cape")
	float CapeIdleWind = 1.5f;

	/** Detachable cape (deathknight): its own skinned mesh on the hero skeleton, following the body's pose (leader pose),
	 *  with its own Chaos cloth. C toggles it; taking it off also suspends its cloth. -NyabloCape=0 starts without it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Cape")
	TObjectPtr<USkeletalMesh> CapeAsset;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Cape")
	bool bCapeOn = true;

	UFUNCTION(BlueprintCallable, Category = "Nyablo|Cape")
	void SetCapeOn(bool bOn);

	/** Shockwave skill (Q / RMB / K): ground slam that damages and knocks back everything around the hero. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Skill")
	TObjectPtr<UNiagaraSystem> SkillVFX;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Skill")
	float SkillVFXScale = 1.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Skill")
	float SkillCooldown = 4.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Skill")
	float SkillRadius = 450.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Skill")
	float SkillDamage = 35.f;

	/** Shockwave shove = AttackKnockback x this. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Skill")
	float SkillKnockbackPower = 2.5f;

	/** Camera zoom-in on a landed blow (deg of FOV, x combo weight; skill x2), easing back over FovKickSeconds. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Camera")
	float FovKickDegrees = 1.5f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Camera")
	float FovKickSeconds = 0.22f;

	/** Moving cancels a swing only this long (s, swing time) after its hit frame. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combo")
	float RecoveryCancelDelay = 0.15f;

	float GetSkillReadyFraction() const { return SkillCooldown > 0.f ? 1.f - FMath::Clamp(SkillCooldownLeft / SkillCooldown, 0.f, 1.f) : 1.f; }

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;

protected:
	virtual void Die() override;
	virtual void OnAttackHit() override;
	virtual void OnDealtHit(int32 Targets) override;
	virtual void OnTookHit(float Amount) override;
	virtual bool WantsRecoveryCancel() const override { return bAttackQueued && bHoldCancel; }
	void UseSkill();
	void Shake(float Strength, float Seconds);

	void Move(const FInputActionValue& Value);
	void MoveReleased(const FInputActionValue& Value);
	/** Moving cancels a normal swing at any point (10-01) once the move key is pressed after the swing started; a key
	 *  already held when the swing started (attacking on the run) cancels only RecoveryCancelDelay after the hit.
	 *  The shockwave skill keeps the old after-hit rule so its cooldown is not wasted. */
	bool TryMoveCancel();
	bool bMoveHeldAtSwingStart = false;
	/** -NyabloCancelAt=<s>: auto test presses a fresh move this long into every normal swing. */
	float AutoCancelAt = -1.f;
	/** After an auto-test cancel: walk sideways this long before attacking again, like a player stepping out. */
	float AutoCancelMoveLeft = 0.f;
	void Attack();
	void Zoom(const FInputActionValue& Value);
	bool StartComboAttack();
	void ApplyClip(int32 Index);
	void AutoDrive(float DeltaSeconds);
	void MeasureHipJump();

	UPROPERTY(VisibleAnywhere, Category = "Nyablo|Camera")
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(VisibleAnywhere, Category = "Nyablo|Camera")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(VisibleAnywhere, Category = "Nyablo|Cape")
	TObjectPtr<UWindDirectionalSourceComponent> CapeWind;

	UPROPERTY(VisibleAnywhere, Category = "Nyablo|Cape")
	TObjectPtr<USkeletalMeshComponent> CapeMesh;

	void ToggleCape() { SetCapeOn(!bCapeOn); }

	float CapeGustLeft = 0.f;
	void UpdateCapeWind(float DeltaSeconds);

	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> Mapping;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> MoveAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> AttackAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> SkillAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ZoomAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> CapeAction;

	float TargetCameraDistance = 0.f;

	float SkillCooldownLeft = 0.f;
	bool bSkillSwing = false;
	float ShakeLeft = 0.f;
	float ShakeTotal = 0.f;
	float ShakeStrength = 0.f;
	float FovKickLeft = 0.f;
	float FovKickAmount = 0.f;
	float BaseFov = -1.f;

	FVector2D LastMoveInput = FVector2D::ZeroVector;
	/** Attack pressed mid-swing: fires as soon as the current swing ends (click-spam feels responsive). */
	bool bAttackQueued = false;
	int32 ComboIndex = 0;
	float SinceAttackEnd = 100.f;
	float BaseAttackDamage = 0.f;
	float CurrentDamageScale = 1.f;
	/** AttackAnim segment set on the level actor (Tripo slash), used when a combo index is invalid. */
	FNyabloAttackClip DefaultClip;
	bool bAutoTest = false;
	/** Impact look-dev overrides (4-33, < 0 = keep the clip's): -NyabloFollow= -NyabloHold= -NyabloRecover= (x PlayRate)
	 *  -NyabloAttackerStop=0|1 -NyabloHoldCancel=0|1 */
	float OverrideFollow = -1.f;
	float OverrideHold = -1.f;
	float OverrideRecover = -1.f;
	/** Look-dev overrides for the one-hand combo clips (10-01): -NyabloWindup= -NyabloStrike= -NyabloApexFrames=
	 *  -NyabloApexRate= -NyabloFollowRate= (absolute rates; < 0 = clip value). */
	float OverrideWindup = -1.f;
	float OverrideStrike = -1.f;
	float OverrideApexFrames = -1.f;
	float OverrideApexRate = -1.f;
	float OverrideFollowRate = -1.f;
	bool bHoldCancel = true;
	float AutoTime = 0.f;
	int32 AutoShot = 0;
	FVector LastHipOffset = FVector::ZeroVector;
	float MaxHipJump = 0.f;
	TArray<FVector> LastJointRel;
	int32 LastPlayCount = 0;
	float MaxSwitchJump = 0.f;
	float MaxSteadyJump = 0.f;
};
