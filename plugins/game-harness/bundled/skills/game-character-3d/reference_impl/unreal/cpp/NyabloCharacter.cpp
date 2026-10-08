#include "NyabloCharacter.h"

#include "Animation/AnimSequence.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/OverlapResult.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstance.h"
#include "NiagaraComponent.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "NyabloAnimInstance.h"
#include "NyabloGameMode.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"

DEFINE_LOG_CATEGORY_STATIC(LogNyablo, Log, All);

ANyabloCharacter::ANyabloCharacter()
{
	PrimaryActorTick.bCanEverTick = true;
	bUseControllerRotationYaw = false;

	UCharacterMovementComponent* Move = GetCharacterMovement();
	Move->bOrientRotationToMovement = true;
	Move->RotationRate = FRotator(0.f, 720.f, 0.f);
	Move->MaxAcceleration = 4000.f;
	Move->BrakingDecelerationWalking = 4000.f;

	GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);

	WeaponRight = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("WeaponRight"));
	WeaponRight->SetupAttachment(GetMesh(), TEXT("R_Hand"));
	WeaponRight->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	WeaponLeft = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("WeaponLeft"));
	WeaponLeft->SetupAttachment(GetMesh(), TEXT("L_Hand"));
	WeaponLeft->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void ANyabloCharacter::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);

	if (CharacterMesh)
	{
		GetMesh()->SetSkeletalMeshAsset(CharacterMesh);
		// Capsule from the reference-pose bounds; the mesh origin sits at the feet.
		const FBoxSphereBounds Bounds = CharacterMesh->GetBounds();
		const float MinZ = Bounds.Origin.Z - Bounds.BoxExtent.Z;
		const float HalfHeight = FMath::Max(Bounds.BoxExtent.Z, 40.f);
		GetCapsuleComponent()->SetCapsuleSize(HalfHeight * 0.33f, HalfHeight);
		GetMesh()->SetRelativeLocation(FVector(0.f, 0.f, -HalfHeight - MinZ));
	}

	WeaponRight->SetStaticMesh(WeaponRightMesh);
	WeaponRight->SetRelativeTransform(WeaponRightTransform);
	WeaponLeft->SetStaticMesh(WeaponLeftMesh);
	WeaponLeft->SetRelativeTransform(WeaponLeftTransform);

	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
	if (IdleAnim)
	{
		// Also shows the idle pose in the editor viewport.
		GetMesh()->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		GetMesh()->OverrideAnimationData(IdleAnim, true, true, 0.f, 1.f);
	}
}

void ANyabloCharacter::BeginPlay()
{
	Super::BeginPlay();
	Health = MaxHealth;
	Action = ENyabloAction::Locomotion;
	bLogTip = FParse::Param(FCommandLine::Get(), TEXT("NyabloTipLog"));
	CurrentLoop = nullptr;
	// game: crossfading clip player (4-28); the editor preview keeps the single-node idle from OnConstruction
	GetMesh()->SetAnimationMode(EAnimationMode::AnimationBlueprint);
	GetMesh()->SetAnimInstanceClass(UNyabloAnimInstance::StaticClass());
	// pose after the actor's own Tick: the swing-end lunge moves the capsule and switches the clip in the same tick,
	// an earlier pose would show the old clip's step-in on top of the moved capsule for one frame (4-27)
	GetMesh()->PrimaryComponentTick.AddPrerequisite(this, PrimaryActorTick);
	BaseMeshQuat = GetMesh()->GetRelativeRotation().Quaternion();
	if (const UStaticMesh* Weapon = WeaponRight->GetStaticMesh())
	{
		// blade tip = far end of the longest bounding-box axis, measured from the grip pivot
		const FBox Box = Weapon->GetBoundingBox();
		const FVector Size = Box.GetSize();
		const int32 Axis = Size.X >= Size.Y && Size.X >= Size.Z ? 0 : (Size.Y >= Size.Z ? 1 : 2);
		BladeTipLocal = Box.GetCenter();
		BladeTipLocal[Axis] = FMath::Abs(Box.Max[Axis]) >= FMath::Abs(Box.Min[Axis]) ? Box.Max[Axis] : Box.Min[Axis];
	}
}

void ANyabloCharacter::UpdateTrail(float Position, float Length)
{
	if (!TrailVFX || !WeaponRight->GetStaticMesh())
	{
		return;
	}
	const float Hit = AttackHitFraction * Length;
	// time-warped swings: the ribbon starts with the snap; otherwise TrailLead real seconds before the hit
	const float Start = AttackStrikeFraction >= 0.f ? AttackStrikeFraction * Length : Hit - TrailLead * AttackPlayRate;
	if (!bTrailStarted && Position >= Start)
	{
		bTrailStarted = true;
		const FVector Blade = BladeTipLocal;   // grip pivot -> tip, weapon space
		const FQuat Turn = FQuat::FindBetweenNormals(FVector::UpVector, Blade.GetSafeNormal()) * FQuat(FVector::UpVector, FMath::DegreesToRadians(TrailRoll));
		// relative to the weapon component, so the scale is in weapon-mesh units: demo blade length -> this blade length
		const float Scale = Blade.Size() / FMath::Max(TrailRefLength, 1.f) * TrailScale;
		ActiveTrail = UNiagaraFunctionLibrary::SpawnSystemAttached(TrailVFX, WeaponRight, NAME_None, FVector::ZeroVector, Turn.Rotator(),
			FVector(Scale), EAttachLocation::KeepRelativeOffset, true, ENCPoolMethod::None, true, true);
	}
	if (ActiveTrail && Position >= Hit + TrailHold * AttackPlayRate)
	{
		StopTrail();
	}
}

UNyabloAnimInstance* ANyabloCharacter::GetBlendAnim() const
{
	return Cast<UNyabloAnimInstance>(GetMesh()->GetAnimInstance());
}

void ANyabloCharacter::AnimPlay(UAnimSequence* Anim, bool bLoop, float BlendTime, float StartTime, float Rate, float MaxTime)
{
	if (UNyabloAnimInstance* Blend = GetBlendAnim())
	{
		Blend->Play(Anim, bLoop, BlendTime, StartTime, Rate, MaxTime);
		return;
	}
	GetMesh()->PlayAnimation(Anim, bLoop);
	GetMesh()->SetPosition(StartTime, false);
	GetMesh()->SetPlayRate(Rate);
}

float ANyabloCharacter::AnimPosition() const
{
	const UNyabloAnimInstance* Blend = GetBlendAnim();
	return Blend ? Blend->GetPosition() : GetMesh()->GetPosition();
}

float ANyabloCharacter::AnimRate() const
{
	const UNyabloAnimInstance* Blend = GetBlendAnim();
	return Blend ? Blend->GetRate() : GetMesh()->GetPlayRate();
}

void ANyabloCharacter::AnimSetRate(float Rate)
{
	if (UNyabloAnimInstance* Blend = GetBlendAnim())
	{
		Blend->SetRate(Rate);
		return;
	}
	GetMesh()->SetPlayRate(Rate);
}

float ANyabloCharacter::SwingProgress() const
{
	if (!AttackAnim)
	{
		return 0.f;
	}
	const float Span = FMath::Max(AttackEndFraction - AttackStartFraction, 0.01f);
	return FMath::Clamp((AnimPosition() / AttackAnim->GetPlayLength() - AttackStartFraction) / Span, 0.f, 1.f);
}

float ANyabloCharacter::CurrentAttackRate() const
{
	if (AttackStrikeFraction < 0.f || !AttackAnim)
	{
		return AttackPlayRate;
	}
	const float Fraction = AnimPosition() / FMath::Max(AttackAnim->GetPlayLength(), 0.01f);
	if (Fraction < AttackHitFraction)
	{
		if (Fraction >= AttackStrikeFraction)
		{
			return AttackStrikeRate;
		}
		return AttackApexFraction >= 0.f && Fraction >= AttackApexFraction ? AttackApexRate : AttackWindupRate;
	}
	if (AttackFollowFraction < 0.f)
	{
		return AttackPlayRate;
	}
	// hit -> snap on -> hold the extended pose -> slow recovery (4-33)
	return !bHoldStarted ? AttackFollowRate : (HoldLeft > 0.f ? 0.f : AttackRecoverRate);
}

FVector ANyabloCharacter::HipInActorSpace() const
{
	return GetActorTransform().InverseTransformPosition(GetMesh()->GetBoneLocation(TEXT("Hip")));
}

void ANyabloCharacter::CancelAttack()
{
	if (Action != ENyabloAction::Attacking)
	{
		return;
	}
	// put the capsule under the drawn hip (relative to where the locomotion pose had it when the swing began): the
	// strike carries the hip up to ~1 m ahead with step + weight transfer, and a partial catch-up left the body far
	// ahead of the capsule, which swung round when the next swing turned the actor (134 cm pose jump)
	FVector Local = HipInActorSpace() - HipAtAttackStart;
	Local.Z = 0.f;
	const FVector Step = AttackAnim ? GetActorRotation().RotateVector(Local) : FVector::ZeroVector;
	if (!Step.IsNearlyZero())
	{
		const FVector Before = GetActorLocation();
		AddActorWorldOffset(Step, true);
		if (UNyabloAnimInstance* Blend = GetBlendAnim())
		{
			Blend->ShiftRoots(-GetMesh()->GetComponentTransform().InverseTransformVector(GetActorLocation() - Before));
		}
	}
	UE_LOG(LogTemp, Log, TEXT("NYABLO_CANCEL anim=%s pos=%.2f progress=%.2f hit=%d step=%.0fcm"), AttackAnim ? *AttackAnim->GetName() : TEXT("none"),
		AnimPosition(), SwingProgress(), bHitApplied ? 1 : 0, Step.Size2D());
	Action = ENyabloAction::Locomotion;
	CurrentLoop = nullptr;
	LastSwingEndFrame = GFrameCounter;
	StopTrail();
}

void ANyabloCharacter::StopTrail()
{
	if (ActiveTrail)
	{
		ActiveTrail->Deactivate();   // the ribbon already drawn fades out on its own
		ActiveTrail = nullptr;
	}
}

FVector ANyabloCharacter::GetBladeTip() const
{
	return WeaponRight->GetStaticMesh() ? WeaponRight->GetComponentTransform().TransformPosition(BladeTipLocal)
		: GetMesh()->GetSocketLocation(TEXT("R_Hand"));
}

void ANyabloCharacter::SpawnSwingVFX(const FVector& TipTravel)
{
	bSwingVFXSpawned = true;
	// arc plane = forward + the blade's travel across the body (diagonal cut -> tilted arc), centred on the body,
	// which by now has stepped in part of the clip's lunge (the capsule catches up only at the end, 4-27)
	const FVector Fwd = GetActorForwardVector();
	const FVector Across = TipTravel - Fwd * (TipTravel | Fwd);
	FQuat Rot = Across.SizeSquared() > 1.f ? FRotationMatrix::MakeFromXY(Fwd, Across * SwingVFXSweepSign).ToQuat() : GetActorQuat();
	Rot = Rot * SwingVFXRotationOffset.Quaternion();
	const float Progress = SwingProgress();
	const FVector Where = GetChestLocation() + Fwd * 60.f + GetActorRotation().RotateVector(AttackLunge) * Progress;
	SpawnVFX(SwingVFX, Where, Rot.Rotator(), SwingVFXScale);
	UE_LOG(LogNyablo, Log, TEXT("NYABLO_SWINGVFX %s travel=%s rot=%s"), *GetName(), *GetActorQuat().UnrotateVector(TipTravel).ToCompactString(),
		*(GetActorQuat().Inverse() * Rot).Rotator().ToCompactString());
}

void ANyabloCharacter::StartHitReaction(const FVector& Away, float Distance, float Degrees)
{
	PushOffset = Away * Distance;
	PushLeft = Distance > 0.f ? KnockbackSeconds : 0.f;
	if (Degrees > 0.f && !IsDead())
	{
		// lean the top of the body along Away (axis in actor space; relative rotation = flinch * base)
		FlinchAxis = FVector::CrossProduct(FVector::UpVector, GetActorQuat().UnrotateVector(Away)).GetSafeNormal();
		FlinchAngle = FMath::DegreesToRadians(Degrees);
		FlinchLeft = FlinchAxis.IsNearlyZero() ? 0.f : FlinchSeconds;
	}
}

void ANyabloCharacter::UpdateHitReaction(float DeltaSeconds)
{
	// dilated DeltaSeconds: hit-stop freezes the shove too, then it snaps out
	if (PushLeft > 0.f)
	{
		const float Total = FMath::Max(KnockbackSeconds, 0.01f);
		const float T0 = 1.f - PushLeft / Total;
		PushLeft = FMath::Max(0.f, PushLeft - DeltaSeconds);
		const float T1 = 1.f - PushLeft / Total;
		// ease-out: covered fraction s(t) = t(2 - t), fastest at the blow
		AddActorWorldOffset(PushOffset * (T1 * (2.f - T1) - T0 * (2.f - T0)), true);
	}
	if (IsDead())
	{
		return;
	}
	bool bRotating = false;
	FQuat Flinch = FQuat::Identity;
	if (FlinchLeft > 0.f)
	{
		FlinchLeft = FMath::Max(0.f, FlinchLeft - DeltaSeconds);
		const float U = 1.f - FlinchLeft / FMath::Max(FlinchSeconds, 0.01f);
		const float Shape = FMath::Sin(FMath::Min(U / 0.15f, 1.f) * HALF_PI) * FMath::Square(1.f - U);   // snap out, ease home
		Flinch = FQuat(FlinchAxis, FlinchAngle * Shape);
		bRotating = true;
	}
	if (VisualTurnYaw != 0.f)
	{
		VisualTurnYaw = FMath::FInterpTo(VisualTurnYaw, 0.f, DeltaSeconds, VisualTurnSpeed);
		VisualTurnYaw = FMath::Abs(VisualTurnYaw) < 0.5f ? 0.f : VisualTurnYaw;
		bRotating = true;
	}
	if (bRotating || bMeshRotated)
	{
		GetMesh()->SetRelativeRotation(FQuat(FVector::UpVector, FMath::DegreesToRadians(VisualTurnYaw)) * Flinch * BaseMeshQuat);
		bMeshRotated = bRotating;
	}
}

float ANyabloCharacter::GetBodyHeight() const
{
	return GetCapsuleComponent()->GetScaledCapsuleHalfHeight() * 2.f;
}

FVector ANyabloCharacter::GetChestLocation() const
{
	return GetActorLocation() + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() * 0.35f);
}

void ANyabloCharacter::SpawnVFX(UNiagaraSystem* System, const FVector& Location, const FRotator& Rotation, float Scale) const
{
	if (System)
	{
		UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), System, Location, Rotation, FVector(Scale), true, true);
	}
}

void ANyabloCharacter::StartHitStop(float Seconds)
{
	if (Seconds > 0.f && !IsDead())
	{
		HitStopLeft = FMath::Max(HitStopLeft, Seconds);
		CustomTimeDilation = 0.05f;
	}
}

void ANyabloCharacter::FaceLocation(const FVector& Target)
{
	const FVector To = Target - GetActorLocation();
	if (!To.IsNearlyZero())
	{
		// the capsule (hit direction) turns at once; the body catches up over ~0.1 s (4-28: an instant 90-180 deg flip
		// toward the next target read as a pop)
		const float OldYaw = GetActorRotation().Yaw;
		SetActorRotation(FRotator(0.f, To.Rotation().Yaw, 0.f));
		if (!IsDead())
		{
			VisualTurnYaw = FMath::Clamp(FRotator::NormalizeAxis(VisualTurnYaw + OldYaw - GetActorRotation().Yaw), -179.f, 179.f);
		}
	}
}

void ANyabloCharacter::PlayLoop(UAnimSequence* Anim)
{
	if (Anim && Anim != CurrentLoop)
	{
		AnimPlay(Anim, true, bLastPlayWasAttack ? BlendOutOfAttack : BlendLoops);
		bLastPlayWasAttack = false;
		CurrentLoop = Anim;
	}
}

void ANyabloCharacter::UpdateAnimation(float DeltaSeconds)
{
	const float Speed = GetVelocity().Size2D();
	if (Speed > 30.f && MoveAnim)
	{
		PlayLoop(MoveAnim);
		AnimSetRate(FMath::Clamp(Speed / FMath::Max(MoveAnimSpeed, 1.f), 0.5f, 2.5f));
	}
	else
	{
		IdleTime += DeltaSeconds;
		if (IdleVariantAnim && IdleTime >= IdleVariantDelay)
		{
			if (CurrentLoop != IdleVariantAnim)
			{
				AnimPlay(IdleVariantAnim, false, BlendLoops);
				CurrentLoop = IdleVariantAnim;
			}
			if (IdleTime >= IdleVariantDelay + IdleVariantAnim->GetPlayLength())
			{
				IdleTime = 0.f;
				PlayLoop(IdleAnim);
			}
		}
		else
		{
			PlayLoop(IdleAnim);
		}
		AnimSetRate(1.f);
		return;
	}
	IdleTime = 0.f;
}

bool ANyabloCharacter::StartAttack()
{
	if (Action != ENyabloAction::Locomotion)
	{
		return false;
	}
	Action = ENyabloAction::Attacking;
	ActionTime = 0.f;
	IdleTime = 0.f;
	bHitApplied = false;
	bHoldStarted = false;
	HoldLeft = 0.f;
	GetCharacterMovement()->StopMovementImmediately();
	CurrentLoop = nullptr;
	bSwingVFXSpawned = false;   // spawned from Tick just before the hit, along the blade
	StopTrail();
	bTrailStarted = false;
	LastBladeTip = GetBladeTip();
	LastGrip = WeaponRight->GetComponentLocation();
	if (AttackAnim)
	{
		// a swing that ended this very frame counts as the previous clip (its end already queued an idle Play)
		const bool bFromSwing = bLastPlayWasAttack || LastSwingEndFrame == GFrameCounter;
		const float Blend = !bFromSwing ? BlendIntoAttack : (AttackAnim == LastAttackAnim ? BlendComboSame : BlendComboOther);
		// fading out after the window, the clip may run ~3 frames past its end, not into the next combo window
		const float Len = AttackAnim->GetPlayLength();
		AnimPlay(AttackAnim, false, Blend, AttackStartFraction * Len,
			AttackStrikeFraction > AttackStartFraction ? AttackWindupRate : AttackPlayRate, AttackEndFraction * Len + 0.1f);
		bLastPlayWasAttack = true;
		LastAttackAnim = AttackAnim;
		AttackStartLocation = GetActorLocation();
		HipAtAttackStart = HipInActorSpace();
	}
	else
	{
		PlayLoop(IdleAnim);
	}
	return true;
}

void ANyabloCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	UpdateHitReaction(DeltaSeconds);
	if (HitStopLeft > 0.f)
	{
		HitStopLeft -= GetWorld()->GetDeltaSeconds();   // undilated by CustomTimeDilation
		if (HitStopLeft <= 0.f)
		{
			CustomTimeDilation = 1.f;
		}
	}
	if (FootstepVFX && Action == ENyabloAction::Locomotion && GetVelocity().Size2D() > 120.f)
	{
		FootstepTimer -= DeltaSeconds;
		if (FootstepTimer <= 0.f)
		{
			FootstepTimer = FootstepInterval;
			const FVector Feet = GetActorLocation() - FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() - 5.f);
			SpawnVFX(FootstepVFX, Feet, GetActorRotation(), 1.f);
		}
	}

	if (FlashTimeLeft > 0.f)
	{
		FlashTimeLeft -= DeltaSeconds;
		if (FlashTimeLeft <= 0.f)
		{
			GetMesh()->SetCustomPrimitiveDataFloat(0, 0.f);
		}
	}

	switch (Action)
	{
	case ENyabloAction::Dead:
		DeadTime += DeltaSeconds;
		if (!GetMesh()->IsSimulatingPhysics())
		{
			// No physics asset from import: fall sideways over 0.35 s, then sink into the floor.
			const float Fall = FMath::Clamp(DeadTime / 0.35f, 0.f, 1.f);
			GetMesh()->SetRelativeRotation(FRotator(0.f, 0.f, 88.f * FMath::Sin(Fall * HALF_PI)));
			if (DeadTime > 2.5f)
			{
				GetMesh()->AddRelativeLocation(FVector(0.f, 0.f, -60.f * DeltaSeconds));
			}
		}
		if (!bPlayerTeam && DeadTime > 6.f)
		{
			Destroy();
		}
		return;

	case ENyabloAction::Stunned:
		StunTimeLeft -= DeltaSeconds;
		if (StunTimeLeft <= 0.f)
		{
			Action = ENyabloAction::Locomotion;
			CurrentLoop = nullptr;
		}
		break;

	case ENyabloAction::Attacking:
	{
		ActionTime += DeltaSeconds;
		bool bFinished = ActionTime > 6.f;
		if (AttackAnim)
		{
			const float Length = AttackAnim->GetPlayLength();
			const float Position = AnimPosition();
			// the hold starts on the frame the snap passes its end: a hard stop, not eased (4-33)
			if (AttackFollowFraction >= 0.f && !bHoldStarted && Position >= AttackFollowFraction * Length)
			{
				bHoldStarted = true;
				HoldLeft = AttackHoldSeconds;
				if (HoldLeft > 0.f)
				{
					AnimSetRate(0.f);
				}
			}
			else if (bHoldStarted && HoldLeft > 0.f)
			{
				HoldLeft -= DeltaSeconds;
			}
			// wind-up -> snap -> recovery (4-28), eased over ~2-3 frames: an instant 2.3x speed step read as a stutter
			const float Rate = FMath::FInterpTo(AnimRate(), CurrentAttackRate(), DeltaSeconds, 30.f);
			if (!FMath::IsNearlyEqual(AnimRate(), Rate))
			{
				AnimSetRate(Rate);
			}
			const FVector Tip = GetBladeTip();
			if (bLogTip)
			{
				// per-frame blade tip speed in the game (4-33 impact check; pair with -UseFixedTimeStep -FPS=30)
				const FVector Grip = WeaponRight->GetComponentLocation();
				UE_LOG(LogTemp, Log, TEXT("NYABLO_TIP anim=%s frame=%.2f rate=%.2f speed=%.1f hand=%.1f hit=%d hold=%d"), *AttackAnim->GetName(),
					Position * AttackAnim->GetSamplingFrameRate().AsDecimal() + 1.f, AnimRate(), (Tip - LastBladeTip).Size(),
					(Grip - LastGrip).Size(), bHitApplied ? 1 : 0, (bHoldStarted && HoldLeft > 0.f) ? 1 : 0);
				LastGrip = Grip;
			}
			if (SwingVFX && !bSwingVFXSpawned && Position >= AttackHitFraction * Length - SwingVFXLead * AttackPlayRate)
			{
				SpawnSwingVFX(Tip - LastBladeTip);
			}
			LastBladeTip = Tip;
			UpdateTrail(Position, Length);
			if (!bHitApplied && Position >= AttackHitFraction * Length)
			{
				OnAttackHit();
			}
			bFinished |= Position >= AttackEndFraction * Length;
			// a queued next swing cuts the recovery once the hold is over (4-33)
			bFinished |= bHoldStarted && HoldLeft <= 0.f && WantsRecoveryCancel();
		}
		else
		{
			if (!bHitApplied && ActionTime >= TimedAttackWindup)
			{
				OnAttackHit();
			}
			bFinished |= ActionTime >= TimedAttackDuration;
		}
		if (bFinished)
		{
			if (AttackAnim && !AttackLunge.IsNearlyZero())
			{
				// the swing's hip travel is in the clip (4-27): move the capsule under the body before the next clip,
				// which starts re-zeroed again -> the step-in stays, nothing pops back
				const FVector Before = GetActorLocation();
				AddActorWorldOffset(GetActorRotation().RotateVector(AttackLunge), true);
				// the clips still fading / starting are drawn relative to the capsule: move them back by what it moved
				if (UNyabloAnimInstance* Blend = GetBlendAnim())
				{
					Blend->ShiftRoots(-GetMesh()->GetComponentTransform().InverseTransformVector(GetActorLocation() - Before));
				}
			}
			if (AttackAnim)
			{
				UE_LOG(LogTemp, Log, TEXT("NYABLO_LUNGE anim=%s pos=%.2f moved=%.0fcm lunge=%s"), *AttackAnim->GetName(), AnimPosition(),
					FVector::Dist2D(GetActorLocation(), AttackStartLocation), *AttackLunge.ToCompactString());
			}
			Action = ENyabloAction::Locomotion;
			CurrentLoop = nullptr;
			LastSwingEndFrame = GFrameCounter;
		}
		break;
	}

	default:
		break;
	}

	if (Action != ENyabloAction::Attacking)
	{
		StopTrail();   // swing ended, cancelled or interrupted
	}
	if (Action == ENyabloAction::Locomotion)
	{
		UpdateAnimation(DeltaSeconds);
	}
}

void ANyabloCharacter::OnAttackHit()
{
	bHitApplied = true;
	HitActionTime = ActionTime;
	// the hit sphere rides the step-in like the body does (the capsule only catches up when the swing ends)
	const FVector Center = GetActorLocation() + GetActorForwardVector() * AttackReach + GetActorRotation().RotateVector(AttackLunge) * SwingProgress();
	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(NyabloMelee), false, this);
	GetWorld()->OverlapMultiByObjectType(Overlaps, Center, FQuat::Identity, FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(AttackRadius), Params);

	TSet<AActor*> Damaged;
	for (const FOverlapResult& Overlap : Overlaps)
	{
		ANyabloCharacter* Target = Cast<ANyabloCharacter>(Overlap.GetActor());
		if (Target && !Damaged.Contains(Target) && IsHostileTo(Target) && !Target->IsDead())
		{
			Damaged.Add(Target);
			UGameplayStatics::ApplyDamage(Target, AttackDamage, GetController(), this, UDamageType::StaticClass());
		}
	}
	if (Damaged.Num() > 0)
	{
		if (bAttackerHitStop)
		{
			StartHitStop(FMath::Min(HitStopSeconds * AttackPower, 0.12f));
		}
		OnDealtHit(Damaged.Num());
	}
	// nearest living hostile at the hit frame (knockback check: does the combo still reach it?)
	float Nearest = -1.f;
	for (TActorIterator<ANyabloCharacter> It(GetWorld()); It; ++It)
	{
		if (IsHostileTo(*It) && !It->IsDead() && !Damaged.Contains(*It))
		{
			const float D = FVector::Dist2D(It->GetActorLocation(), GetActorLocation());
			Nearest = Nearest < 0.f ? D : FMath::Min(Nearest, D);
		}
	}
	UE_LOG(LogNyablo, Log, TEXT("NYABLO_HIT %s swing hits=%d power=%.1f nearestMissed=%.0fcm"), *GetName(), Damaged.Num(), AttackPower, Nearest);
}

void ANyabloCharacter::Flash(float Strength)
{
	// M_Char reads Custom Primitive Data[0] as "Flash" (adds tinted colour + emissive). No MIDs:
	// dynamic copies of the material lost their texture overrides at runtime (bodies turned dark grey).
	GetMesh()->SetCustomPrimitiveDataFloat(0, Strength);
	FlashTimeLeft = 0.12f;
}

float ANyabloCharacter::TakeDamage(float DamageAmount, FDamageEvent const& DamageEvent, AController* EventInstigator, AActor* DamageCauser)
{
	if (IsDead() || DamageAmount <= 0.f)
	{
		return 0.f;
	}
	Super::TakeDamage(DamageAmount, DamageEvent, EventInstigator, DamageCauser);
	Health = FMath::Max(0.f, Health - DamageAmount);
	Flash(1.5f);
	const FVector Chest = GetChestLocation();
	SpawnVFX(HitVFX, Chest, DamageCauser ? (Chest - DamageCauser->GetActorLocation()).Rotation() : GetActorRotation(), HitVFXScale);
	const ANyabloCharacter* Attacker = Cast<ANyabloCharacter>(DamageCauser);
	const float Power = Attacker ? Attacker->GetAttackPower() : 1.f;
	StartHitStop(FMath::Min(HitStopSeconds * Power, 0.12f));
	OnTookHit(DamageAmount);
	if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
	{
		if (ANyabloHUD* HUD = Cast<ANyabloHUD>(PC->GetHUD()))
		{
			HUD->AddDamageNumber(Chest + FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), DamageAmount, bPlayerTeam);
		}
	}

	if (DamageCauser)
	{
		// ground shove + lean instead of an air launch (4-28). The hero is only nudged, and not at all mid-swing
		// (a launch slid the swinging hero up to 1.5 m).
		const FVector Away = (GetActorLocation() - DamageCauser->GetActorLocation()).GetSafeNormal2D();
		const float Push = (Attacker ? Attacker->AttackKnockback : 25.f) * Power;
		LastHitAway = Away;
		LastHitPower = Power;
		GetCharacterMovement()->StopMovementImmediately();
		if (bPlayerTeam)
		{
			StartHitReaction(Away, Action == ENyabloAction::Attacking ? 0.f : Push * 0.35f, FlinchDegrees * 0.4f);
		}
		else
		{
			StartHitReaction(Away, Push, FlinchDegrees);
		}
	}
	UE_LOG(LogNyablo, Log, TEXT("NYABLO_DAMAGE %s took %.0f hp=%.0f"), *GetName(), DamageAmount, Health);

	if (Health <= 0.f)
	{
		Die();
	}
	else if (!bPlayerTeam)
	{
		// Enemies are interrupted (hit stun); the hero keeps control.
		// the pose freezes where the blow caught it (reads as a stagger; the old idle restart looked untouched)
		Action = ENyabloAction::Stunned;
		StunTimeLeft = 0.35f;
		CurrentLoop = nullptr;
		AnimSetRate(0.f);
	}
	return DamageAmount;
}

void ANyabloCharacter::Die()
{
	Action = ENyabloAction::Dead;
	DeadTime = 0.f;
	Health = 0.f;
	GetCharacterMovement()->DisableMovement();
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	USkeletalMeshComponent* Body = GetMesh();
	if (Body->GetPhysicsAsset())
	{
		// 4-28: falls the way the killing blow pushed (velocity change, cm/s); the old 30 m/s backward kick flung bodies
		PushLeft = 0.f;
		Body->SetRelativeRotation(BaseMeshQuat);
		Body->SetCollisionProfileName(TEXT("Ragdoll"));
		Body->SetSimulatePhysics(true);
		const FVector Away = LastHitAway.IsNearlyZero() ? -GetActorForwardVector() : LastHitAway;
		Body->SetAllPhysicsLinearVelocity(Away * (350.f + 150.f * LastHitPower) + FVector(0.f, 0.f, 180.f));
	}
	if (!Body->IsSimulatingPhysics())
	{
		AnimPlay(IdleAnim, false, 0.15f, 0.f, 0.f);
	}
	UE_LOG(LogNyablo, Log, TEXT("NYABLO_DEATH %s ragdoll=%d"), *GetName(), Body->GetPhysicsAsset() != nullptr);
}
