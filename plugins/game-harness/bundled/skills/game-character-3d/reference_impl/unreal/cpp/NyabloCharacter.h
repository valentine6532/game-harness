#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "NyabloCharacter.generated.h"

class UAnimSequence;
class UNiagaraSystem;
class UMaterialInstanceDynamic;
class USkeletalMesh;
class UStaticMesh;
class UStaticMeshComponent;
class UNyabloAnimInstance;

UENUM(BlueprintType)
enum class ENyabloAction : uint8
{
	Locomotion,
	Attacking,
	Stunned,
	Dead
};

/**
 * Shared hero/enemy body: single-node animation switching (idle / move / attack segment),
 * hand-socket weapons, melee hit window, damage flash, knockback and ragdoll death.
 * Visual data (mesh, clips, weapons, grips) is assigned by Scripts/ue_build_plaza.py.
 */
UCLASS()
class NYABLO_API ANyabloCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ANyabloCharacter();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Visual")
	TObjectPtr<USkeletalMesh> CharacterMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	TObjectPtr<UAnimSequence> IdleAnim;

	/** Played once after standing still for IdleVariantDelay seconds, then back to IdleAnim (4-27). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	TObjectPtr<UAnimSequence> IdleVariantAnim;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float IdleVariantDelay = 8.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	TObjectPtr<UAnimSequence> MoveAnim;

	/** Long Tripo clip; only [AttackStartFraction, AttackEndFraction] is played. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	TObjectPtr<UAnimSequence> AttackAnim;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float AttackStartFraction = 28.f / 198.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float AttackHitFraction = 64.f / 198.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float AttackEndFraction = 92.f / 198.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float AttackPlayRate = 1.6f;

	/** Ground speed (cm/s) at which MoveAnim plays at rate 1. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float MoveAnimSpeed = 450.f;

	/** Crossfade times (s, 4-28; UNyabloAnimInstance): idle/run -> swing, swing -> same-clip swing (combo),
	 *  swing -> other-clip swing (finisher), swing -> idle/run, idle <-> run. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float BlendIntoAttack = 0.09f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float BlendComboSame = 0.08f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float BlendComboOther = 0.18f;   // finisher <-> combo: crouched slam end vs upright start

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float BlendOutOfAttack = 0.2f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float BlendLoops = 0.2f;

	/** Used when AttackAnim is empty (archer): wind-up seconds before the hit, total action seconds. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float TimedAttackWindup = 0.7f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Anim")
	float TimedAttackDuration = 1.1f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combat")
	float MaxHealth = 100.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Nyablo|Combat")
	float Health = 100.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combat")
	float AttackDamage = 25.f;

	/** Melee hit sphere: centre this far in front of the capsule, with this radius (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combat")
	float AttackReach = 150.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combat")
	float AttackRadius = 120.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combat")
	float WalkSpeed = 450.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Combat")
	bool bPlayerTeam = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Weapon")
	TObjectPtr<UStaticMesh> WeaponRightMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Weapon")
	FTransform WeaponRightTransform;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Weapon")
	TObjectPtr<UStaticMesh> WeaponLeftMesh;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Weapon")
	FTransform WeaponLeftTransform;

	/** Fired at the start of a melee swing, in front of the chest, facing the swing (e.g. NS_*Slash_OnlySlash). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	TObjectPtr<UNiagaraSystem> SwingVFX;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float SwingVFXScale = 1.f;

	/** Spawned on this character's body when it takes damage. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	TObjectPtr<UNiagaraSystem> HitVFX;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float HitVFXScale = 1.f;

	/** Dust puff at the feet while moving. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	TObjectPtr<UNiagaraSystem> FootstepVFX;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float FootstepInterval = 0.32f;

	/** Victim hit-stop duration (real seconds); attackers can opt out with bAttackerHitStop. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Feel")
	float HitStopSeconds = 0.07f;

	/** Hit reaction (4-28): this character's blows shove the victim this far (cm, x AttackPower) over KnockbackSeconds,
	 *  along the ground. The old air launch (600 cm/s) threw enemies ~2 m, out of reach of the next combo swing. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Feel")
	float AttackKnockback = 45.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Feel")
	float KnockbackSeconds = 0.16f;

	/** No hit-react clips: a struck body leans away from the blow (pivot at the feet) and springs back. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Feel")
	float FlinchDegrees = 16.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Feel")
	float FlinchSeconds = 0.34f;

	/** FaceLocation turns the capsule at once; the drawn body follows at this FInterpTo speed (4-28). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|Feel")
	float VisualTurnSpeed = 22.f;

	/** SwingVFX appears this many real seconds before the hit frame, laid along the blade's travel (was: at wind-up start,
	 *  flat in front of the chest, whatever the cut direction). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float SwingVFXLead = 0.06f;

	/** +1 / -1: which way the SwingVFX asset sweeps along its local Y. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float SwingVFXSweepSign = 1.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	FRotator SwingVFXRotationOffset = FRotator::ZeroRotator;

	/** Blade trail (SwordTrailVFX ribbon, 4-28): attached along the right weapon from TrailLead s before the hit frame
	 *  to TrailHold s after it, so the 1-2 frame cut draws its arc through the target. The pack's ribbons span the
	 *  demo sword's +Z (TrailRefLength cm); they are turned onto this blade's axis and scaled to its length. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	TObjectPtr<UNiagaraSystem> TrailVFX;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float TrailLead = 0.12f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float TrailHold = 0.1f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float TrailRefLength = 118.f;

	/** Extra turn about the blade axis (deg) and length factor for the trail. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float TrailRoll = 0.f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Nyablo|VFX")
	float TrailScale = 1.f;

	float GetAttackPower() const { return AttackPower; }

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual float TakeDamage(float DamageAmount, struct FDamageEvent const& DamageEvent, AController* EventInstigator, AActor* DamageCauser) override;

	UFUNCTION(BlueprintCallable, Category = "Nyablo")
	bool StartAttack();

	/** Re-apply mesh / capsule / weapons after properties were set from an editor script. */
	UFUNCTION(BlueprintCallable, CallInEditor, Category = "Nyablo")
	void RefreshVisuals() { OnConstruction(GetActorTransform()); }

	bool IsDead() const { return Action == ENyabloAction::Dead; }
	bool IsBusy() const { return Action != ENyabloAction::Locomotion; }
	float GetHealthFraction() const { return MaxHealth > 0.f ? Health / MaxHealth : 0.f; }
	float GetBodyHeight() const;
	bool IsHostileTo(const ANyabloCharacter* Other) const { return Other && Other->bPlayerTeam != bPlayerTeam; }
	void FaceLocation(const FVector& Target);
	void StartHitStop(float Seconds);
	FVector GetChestLocation() const;

protected:
	virtual void OnAttackHit();
	virtual void Die();
	/** Hooks for camera feedback (hero overrides). */
	virtual void OnDealtHit(int32 Targets) {}
	virtual void OnTookHit(float Amount) {}
	void SpawnVFX(UNiagaraSystem* System, const FVector& Location, const FRotator& Rotation, float Scale) const;

	void PlayLoop(UAnimSequence* Anim);
	/** Clip playback through the crossfading instance in game (single-node player in the editor preview). */
	UNyabloAnimInstance* GetBlendAnim() const;
	void AnimPlay(UAnimSequence* Anim, bool bLoop, float BlendTime, float StartTime = 0.f, float Rate = 1.f, float MaxTime = 0.f);
	float AnimPosition() const;
	float AnimRate() const;
	void AnimSetRate(float Rate);
	/** 0..1 through the current swing window (the body has stepped in this share of AttackLunge). */
	float SwingProgress() const;
	bool bLastPlayWasAttack = false;
	uint64 LastSwingEndFrame = 0;
	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> LastAttackAnim;
	void UpdateAnimation(float DeltaSeconds);
	void Flash(float Strength);

	UPROPERTY(VisibleAnywhere, Category = "Nyablo|Weapon")
	TObjectPtr<UStaticMeshComponent> WeaponRight;

	UPROPERTY(VisibleAnywhere, Category = "Nyablo|Weapon")
	TObjectPtr<UStaticMeshComponent> WeaponLeft;

	UPROPERTY(Transient)
	TObjectPtr<UAnimSequence> CurrentLoop;

	ENyabloAction Action = ENyabloAction::Locomotion;
	float ActionTime = 0.f;
	bool bHitApplied = false;
	float FlashTimeLeft = 0.f;
	float StunTimeLeft = 0.f;
	float DeadTime = 0.f;
	float HitStopLeft = 0.f;
	float FootstepTimer = 0.f;
	float IdleTime = 0.f;
	FVector AttackStartLocation = FVector::ZeroVector;
	/** Hip bone in actor space when the swing began: a cancel moves the capsule by how far the drawn hip has travelled. */
	FVector HipAtAttackStart = FVector::ZeroVector;
	FVector HipInActorSpace() const;
	/** Current swing's body travel (cm, actor space), applied to the capsule when the swing ends (4-27). */
	FVector AttackLunge = FVector::ZeroVector;

	/** Weight of the current blow (hero combo: the clip's damage scale): scales hit-stop and knockback. */
	float AttackPower = 1.f;
	/** Time warp of the current swing (see FNyabloAttackClip); < 0 = AttackPlayRate throughout. */
	float AttackStrikeFraction = -1.f;
	float AttackWindupRate = 1.f;
	float AttackStrikeRate = 1.f;
	/** Slow load before the snap (see FNyabloAttackClip::ApexFrames); < 0 = off. */
	float AttackApexFraction = -1.f;
	float AttackApexRate = 1.f;
	/** Impact phases after the hit (see FNyabloAttackClip::FollowFrames); AttackFollowFraction < 0 = off. */
	float AttackFollowFraction = -1.f;
	float AttackFollowRate = 1.f;
	float AttackHoldSeconds = 0.f;
	float AttackRecoverRate = 1.f;
	float HoldLeft = 0.f;
	bool bHoldStarted = false;
	/** false: the attacker skips its own hit-stop and only the target freezes (the hold is the attacker's stop). */
	bool bAttackerHitStop = true;
	/** -NyabloTipLog: NYABLO_TIP per attack frame. */
	bool bLogTip = false;
	FVector LastGrip = FVector::ZeroVector;
	/** Next swing queued: cut the recovery once the hold is over. */
	virtual bool WantsRecoveryCancel() const { return false; }
	float CurrentAttackRate() const;
	/** Direction and weight of the last blow taken: the ragdoll falls that way. */
	FVector LastHitAway = FVector::ZeroVector;
	float LastHitPower = 1.f;
	/** ActionTime at the hit frame (recovery cancel waits a little after it). */
	float HitActionTime = 0.f;

	void StartHitReaction(const FVector& Away, float Distance, float Degrees);
	void UpdateHitReaction(float DeltaSeconds);
	FVector GetBladeTip() const;
	void SpawnSwingVFX(const FVector& TipTravel);

	FVector PushOffset = FVector::ZeroVector;
	float PushLeft = 0.f;
	FVector FlinchAxis = FVector::ZeroVector;
	float FlinchAngle = 0.f;
	float FlinchLeft = 0.f;
	FQuat BaseMeshQuat = FQuat::Identity;
	FVector BladeTipLocal = FVector::ZeroVector;
	FVector LastBladeTip = FVector::ZeroVector;
	bool bSwingVFXSpawned = false;
	float VisualTurnYaw = 0.f;
	bool bMeshRotated = false;

	void UpdateTrail(float Position, float Length);
	void StopTrail();
	/** End the current swing now and hand over to locomotion (10-01 move cancel): the capsule takes the part of the
	 *  step-in the body has already made, so the blend out starts from where the body is drawn. */
	void CancelAttack();

	UPROPERTY(Transient)
	TObjectPtr<class UNiagaraComponent> ActiveTrail;

	bool bTrailStarted = false;
};
