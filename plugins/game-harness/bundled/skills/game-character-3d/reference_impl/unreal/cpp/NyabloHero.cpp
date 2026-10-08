#include "NyabloHero.h"

#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "EngineUtils.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputActionValue.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Engine/OverlapResult.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/CommandLine.h"
#include "NiagaraSystem.h"
#include "NyabloAnimInstance.h"
#include "Animation/AnimSequence.h"
#include "TimerManager.h"
#include "UnrealClient.h"
#include "Components/WindDirectionalSourceComponent.h"

DEFINE_LOG_CATEGORY_STATIC(LogNyabloHero, Log, All);

ANyabloHero::ANyabloHero()
{
	bPlayerTeam = true;
	bAttackerHitStop = false;   // keep the blade moving through the target; the victim still freezes on impact
	AutoPossessPlayer = EAutoReceiveInput::Player0;

	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->SetUsingAbsoluteRotation(true);   // fixed quarter view, independent of the cat's facing
	CameraBoom->bDoCollisionTest = false;
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 8.f;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	Camera->FieldOfView = 50.f;

	CapeWind = CreateDefaultSubobject<UWindDirectionalSourceComponent>(TEXT("CapeWind"));
	CapeWind->SetupAttachment(RootComponent);
	CapeWind->SetUsingAbsoluteRotation(true);
	CapeWind->Strength = 1.f;
	CapeWind->Speed = 0.f;
	CapeWind->MinGustAmount = 0.f;
	CapeWind->MaxGustAmount = 0.1f;

	CapeMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("CapeMesh"));
	CapeMesh->SetupAttachment(GetMesh());
	CapeMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void ANyabloHero::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	CameraBoom->SetRelativeRotation(FRotator(CameraPitch, CameraYaw, 0.f));
	CameraBoom->TargetArmLength = CameraDistance;
}

void ANyabloHero::BeginPlay()
{
	Super::BeginPlay();
	BaseAttackDamage = AttackDamage;
	DefaultClip.Anim = AttackAnim;
	DefaultClip.StartFraction = AttackStartFraction;
	DefaultClip.HitFraction = AttackHitFraction;
	DefaultClip.EndFraction = AttackEndFraction;
	DefaultClip.PlayRate = AttackPlayRate;
	bAutoTest = FParse::Param(FCommandLine::Get(), TEXT("NyabloAuto"));
	FParse::Value(FCommandLine::Get(), TEXT("NyabloFollow="), OverrideFollow);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloHold="), OverrideHold);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloRecover="), OverrideRecover);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloWindup="), OverrideWindup);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloStrike="), OverrideStrike);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloApexFrames="), OverrideApexFrames);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloApexRate="), OverrideApexRate);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloFollowRate="), OverrideFollowRate);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloCancelAt="), AutoCancelAt);
	FParse::Bool(FCommandLine::Get(), TEXT("NyabloAttackerStop="), bAttackerHitStop);
	FParse::Bool(FCommandLine::Get(), TEXT("NyabloHoldCancel="), bHoldCancel);
	// look-dev runs (4-28): arc direction, blade trail asset / roll / length, arc off
	FParse::Value(FCommandLine::Get(), TEXT("NyabloVFXSign="), SwingVFXSweepSign);
	FString TrailPath;
	if (FParse::Value(FCommandLine::Get(), TEXT("NyabloTrail="), TrailPath))
	{
		TrailVFX = TrailPath == TEXT("none") ? nullptr : LoadObject<UNiagaraSystem>(nullptr, *TrailPath);
	}
	FParse::Value(FCommandLine::Get(), TEXT("NyabloTrailRoll="), TrailRoll);
	FParse::Value(FCommandLine::Get(), TEXT("NyabloTrailScale="), TrailScale);
	if (FParse::Param(FCommandLine::Get(), TEXT("NyabloNoArc")))
	{
		SwingVFX = nullptr;
	}
	UE_LOG(LogNyabloHero, Log, TEXT("NYABLO_TRAIL trail=%s bladeTipLocal=%s roll=%.0f scale=%.2f arc=%d"), TrailVFX ? *TrailVFX->GetName() : TEXT("none"),
		*BladeTipLocal.ToCompactString(), TrailRoll, TrailScale, SwingVFX ? 1 : 0);
	// Camera comparison runs: -NyabloCamPitch=-45 -NyabloCamDist=1900
	if (FParse::Value(FCommandLine::Get(), TEXT("NyabloCamPitch="), CameraPitch) | FParse::Value(FCommandLine::Get(), TEXT("NyabloCamDist="), CameraDistance))
	{
		CameraBoom->SetRelativeRotation(FRotator(CameraPitch, CameraYaw, 0.f));
		CameraBoom->TargetArmLength = CameraDistance;
	}
	TargetCameraDistance = CameraDistance;
	if (CapeAsset && CapeMesh)
	{
		CapeMesh->SetSkeletalMesh(CapeAsset);
		CapeMesh->SetLeaderPoseComponent(GetMesh());
		int32 CapeFlag = bCapeOn ? 1 : 0;
		FParse::Value(FCommandLine::Get(), TEXT("NyabloCape="), CapeFlag);   // automated shots of both states
		SetCapeOn(CapeFlag != 0);
		UE_LOG(LogNyabloHero, Log, TEXT("NYABLO_CAPE asset=%s on=%d"), *CapeAsset->GetName(), bCapeOn ? 1 : 0);
	}
	else if (CapeMesh)
	{
		CapeMesh->SetVisibility(false);
	}
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->bShowMouseCursor = !bAutoTest;
		FInputModeGameAndUI Mode;
		Mode.SetHideCursorDuringCapture(false);
		PC->SetInputMode(Mode);
	}
}

void ANyabloHero::SetCapeOn(bool bOn)
{
	bCapeOn = bOn;
	if (!CapeMesh || !CapeMesh->GetSkeletalMeshAsset())
	{
		return;
	}
	CapeMesh->SetVisibility(bOn);
	if (bOn)
	{
		CapeMesh->ResumeClothingSimulation();
		CapeMesh->ForceClothNextUpdateTeleportAndReset();   // no snap from where the cloth was when it was taken off
	}
	else
	{
		CapeMesh->SuspendClothingSimulation();
	}
}

void ANyabloHero::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	MoveAction = NewObject<UInputAction>(this, TEXT("IA_Move"));
	MoveAction->ValueType = EInputActionValueType::Axis2D;
	AttackAction = NewObject<UInputAction>(this, TEXT("IA_Attack"));
	AttackAction->ValueType = EInputActionValueType::Boolean;

	Mapping = NewObject<UInputMappingContext>(this, TEXT("IMC_Nyablo"));
	auto MapMove = [this](const FKey& Key, bool bSwizzle, bool bNegate)
	{
		FEnhancedActionKeyMapping& KeyMapping = Mapping->MapKey(MoveAction, Key);
		if (bSwizzle)
		{
			KeyMapping.Modifiers.Add(NewObject<UInputModifierSwizzleAxis>(this));   // X -> Y
		}
		if (bNegate)
		{
			KeyMapping.Modifiers.Add(NewObject<UInputModifierNegate>(this));
		}
	};
	MapMove(EKeys::W, true, false);
	MapMove(EKeys::S, true, true);
	MapMove(EKeys::D, false, false);
	MapMove(EKeys::A, false, true);
	MapMove(EKeys::Up, true, false);
	MapMove(EKeys::Down, true, true);
	MapMove(EKeys::Right, false, false);
	MapMove(EKeys::Left, false, true);
	Mapping->MapKey(AttackAction, EKeys::LeftMouseButton);
	Mapping->MapKey(AttackAction, EKeys::SpaceBar);
	Mapping->MapKey(AttackAction, EKeys::J);
	SkillAction = NewObject<UInputAction>(this, TEXT("IA_Skill"));
	SkillAction->ValueType = EInputActionValueType::Boolean;
	Mapping->MapKey(SkillAction, EKeys::Q);
	Mapping->MapKey(SkillAction, EKeys::RightMouseButton);
	Mapping->MapKey(SkillAction, EKeys::K);
	ZoomAction = NewObject<UInputAction>(this, TEXT("IA_Zoom"));
	ZoomAction->ValueType = EInputActionValueType::Axis1D;
	Mapping->MapKey(ZoomAction, EKeys::MouseWheelAxis);
	CapeAction = NewObject<UInputAction>(this, TEXT("IA_Cape"));
	CapeAction->ValueType = EInputActionValueType::Boolean;
	Mapping->MapKey(CapeAction, EKeys::C);

	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (UEnhancedInputLocalPlayerSubsystem* Subsystem = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer()))
		{
			Subsystem->AddMappingContext(Mapping, 0);
		}
	}
	if (UEnhancedInputComponent* Input = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		Input->BindAction(MoveAction, ETriggerEvent::Triggered, this, &ANyabloHero::Move);
		Input->BindAction(MoveAction, ETriggerEvent::Completed, this, &ANyabloHero::MoveReleased);
		Input->BindAction(AttackAction, ETriggerEvent::Started, this, &ANyabloHero::Attack);
		Input->BindAction(SkillAction, ETriggerEvent::Started, this, &ANyabloHero::UseSkill);
		Input->BindAction(ZoomAction, ETriggerEvent::Triggered, this, &ANyabloHero::Zoom);
		Input->BindAction(CapeAction, ETriggerEvent::Started, this, &ANyabloHero::ToggleCape);
	}
	else
	{
		UE_LOG(LogNyabloHero, Error, TEXT("NYABLO input component is not UEnhancedInputComponent (check DefaultInput.ini)"));
	}
}

void ANyabloHero::Move(const FInputActionValue& Value)
{
	const FVector2D Input = Value.Get<FVector2D>();
	LastMoveInput = Input;
	if (Input.IsNearlyZero())
	{
		bMoveHeldAtSwingStart = false;
	}
	else
	{
		TryMoveCancel();
	}
	if (IsBusy() || IsDead())
	{
		return;
	}
	const FRotator YawOnly(0.f, CameraYaw, 0.f);
	AddMovementInput(FRotationMatrix(YawOnly).GetUnitAxis(EAxis::X), Input.Y);
	AddMovementInput(FRotationMatrix(YawOnly).GetUnitAxis(EAxis::Y), Input.X);
}

void ANyabloHero::MoveReleased(const FInputActionValue& Value)
{
	LastMoveInput = FVector2D::ZeroVector;
	bMoveHeldAtSwingStart = false;
}

bool ANyabloHero::TryMoveCancel()
{
	if (Action != ENyabloAction::Attacking)
	{
		return false;
	}
	// Move fires every frame a key is held: a key held since the swing began must not cut it off at once, and a
	// held key used to cut every landed swing at its contact frame (4-28) -> for those, wait a moment after the hit
	const bool bAfterHit = bHitApplied && ActionTime - HitActionTime >= RecoveryCancelDelay;
	if (!bAfterHit && (bMoveHeldAtSwingStart || bSkillSwing))
	{
		return false;
	}
	bAttackQueued = false;
	CancelAttack();
	return true;
}

void ANyabloHero::Zoom(const FInputActionValue& Value)
{
	// wheel up (positive) moves the camera in
	TargetCameraDistance = FMath::Clamp(TargetCameraDistance - Value.Get<float>() * CameraZoomStep, CameraMinDistance, CameraMaxDistance);
}

void ANyabloHero::Attack()
{
	if (Action == ENyabloAction::Attacking)
	{
		bAttackQueued = true;
		return;
	}
	if (IsBusy() || IsDead())
	{
		return;
	}
	FHitResult Hit;
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!bAutoTest && PC && PC->GetHitResultUnderCursor(ECC_Visibility, false, Hit))
	{
		FaceLocation(Hit.Location);   // Diablo-style: swing toward the cursor
	}
	StartComboAttack();
}

void ANyabloHero::ApplyClip(int32 Index)
{
	const FNyabloAttackClip& Clip = ComboAttacks.IsValidIndex(Index) && ComboAttacks[Index].Anim ? ComboAttacks[Index] : DefaultClip;
	AttackAnim = Clip.Anim;
	AttackStartFraction = Clip.StartFraction;
	AttackHitFraction = Clip.HitFraction;
	AttackEndFraction = Clip.EndFraction;
	AttackPlayRate = Clip.PlayRate;
	CurrentDamageScale = Clip.DamageScale;
	AttackPower = Clip.DamageScale;
	AttackLunge = Clip.Lunge;
	// look-dev overrides touch only the one-hand combo, not the power finisher / skill (10-01)
	const bool bTune = Clip.Anim && Clip.Anim->GetName().Contains(TEXT("onehand"));
	auto Pick = [bTune](float Override, float Value) { return bTune && Override >= 0.f ? Override : Value; };
	AttackStrikeFraction = Clip.StrikeFraction;
	AttackWindupRate = Pick(OverrideWindup, Clip.WindupRate);
	AttackStrikeRate = Pick(OverrideStrike, Clip.StrikeRate);
	const float Frames = Clip.Anim ? Clip.Anim->GetPlayLength() * Clip.Anim->GetSamplingFrameRate().AsDecimal() : 0.f;
	const float Apex = Pick(OverrideApexFrames, Clip.ApexFrames);
	AttackApexFraction = Apex > 0.f && Frames > 0.f && Clip.StrikeFraction >= 0.f ? Clip.StrikeFraction - Apex / Frames : -1.f;
	AttackApexRate = Pick(OverrideApexRate, Clip.ApexRate);
	// impact phases after the hit (4-33)
	const float Follow = OverrideFollow >= 0.f ? OverrideFollow : Clip.FollowFrames;
	AttackFollowFraction = Follow > 0.f && Frames > 0.f ? Clip.HitFraction + Follow / Frames : -1.f;
	AttackFollowRate = Pick(OverrideFollowRate, Clip.FollowRate > 0.f ? Clip.FollowRate : Clip.StrikeRate);
	AttackHoldSeconds = OverrideHold >= 0.f ? OverrideHold : Clip.HoldSeconds;
	AttackRecoverRate = OverrideRecover >= 0.f ? OverrideRecover * Clip.PlayRate : (Clip.RecoverRate > 0.f ? Clip.RecoverRate : Clip.PlayRate);
}

bool ANyabloHero::StartComboAttack()
{
	if (ComboAttacks.Num() == 0)
	{
		return StartAttack();
	}
	if (SinceAttackEnd > ComboResetSeconds)
	{
		ComboIndex = 0;
	}
	ApplyClip(ComboIndex);
	AttackDamage = BaseAttackDamage * CurrentDamageScale;
	if (!StartAttack())
	{
		return false;
	}
	bMoveHeldAtSwingStart = !LastMoveInput.IsNearlyZero();
	ComboIndex = (ComboIndex + 1) % ComboAttacks.Num();
	CapeGustLeft = CapeGustSeconds;
	return true;
}

void ANyabloHero::UpdateCapeWind(float DeltaSeconds)
{
	if (!CapeWind)
	{
		return;
	}
	// wind blows toward where the cape should go: behind the hero while running, back + up during a swing
	FVector Wind = FVector::ZeroVector;
	const FVector Vel = GetVelocity() * FVector(1.f, 1.f, 0.f);
	const float SpeedFrac = FMath::Clamp(Vel.Size() / FMath::Max(WalkSpeed, 1.f), 0.f, 1.f);
	if (SpeedFrac > 0.05f)
	{
		Wind += -Vel.GetSafeNormal() * CapeTrailWind * SpeedFrac;
	}
	if (CapeGustLeft > 0.f)
	{
		CapeGustLeft -= DeltaSeconds;
		const float T = FMath::Clamp(CapeGustLeft / FMath::Max(CapeGustSeconds, 0.01f), 0.f, 1.f);
		// strongest right after the swing starts, with a little flutter
		const float Flutter = 0.75f + 0.25f * FMath::Sin(GetWorld()->GetTimeSeconds() * 38.f);
		Wind += (-GetActorForwardVector() + FVector(0.f, 0.f, 0.6f)).GetSafeNormal() * CapeGustWind * T * Flutter;
	}
	if (Wind.SizeSquared() < FMath::Square(CapeIdleWind))
	{
		Wind = (-GetActorForwardVector() * 0.6f + GetActorRightVector() * 0.4f).GetSafeNormal() * CapeIdleWind;
	}
	CapeWind->SetWorldRotation(Wind.Rotation());
	CapeWind->SetSpeed(Wind.Size());
}

void ANyabloHero::Die()
{
	Super::Die();
	FTimerHandle Restart;
	GetWorldTimerManager().SetTimer(Restart, [this]()
	{
		UGameplayStatics::OpenLevel(this, FName(*UGameplayStatics::GetCurrentLevelName(this, true)));
	}, 3.f, false);
}

void ANyabloHero::Tick(float DeltaSeconds)
{
	if (bAutoTest)
	{
		MeasureHipJump();
	}
	Super::Tick(DeltaSeconds);
	if (bAutoTest && AutoCancelAt >= 0.f && Action == ENyabloAction::Attacking && !bSkillSwing && ActionTime >= AutoCancelAt
		&& TryMoveCancel())
	{
		AutoCancelMoveLeft = 0.4f;
	}
	if (bAttackQueued && Action != ENyabloAction::Attacking)
	{
		bAttackQueued = false;
		Attack();
	}
	const float RealDt = GetWorld()->GetDeltaSeconds();
	SinceAttackEnd = Action == ENyabloAction::Attacking ? 0.f : SinceAttackEnd + RealDt;
	UpdateCapeWind(RealDt);
	if (TargetCameraDistance > 0.f)
	{
		CameraBoom->TargetArmLength = FMath::FInterpTo(CameraBoom->TargetArmLength, TargetCameraDistance, RealDt, 8.f);
	}
	SkillCooldownLeft = FMath::Max(0.f, SkillCooldownLeft - RealDt);
	if (BaseFov < 0.f)
	{
		BaseFov = Camera->FieldOfView;
	}
	if (FovKickLeft > 0.f)
	{
		FovKickLeft = FMath::Max(0.f, FovKickLeft - RealDt);
		const float U = 1.f - FovKickLeft / FMath::Max(FovKickSeconds, 0.01f);
		Camera->SetFieldOfView(BaseFov - FovKickAmount * FMath::Square(1.f - U));   // snaps in, eases out
	}
	if (ShakeLeft > 0.f)
	{
		ShakeLeft -= RealDt;
		const float Amp = ShakeStrength * FMath::Clamp(ShakeLeft / FMath::Max(ShakeTotal, 0.01f), 0.f, 1.f);
		CameraBoom->SocketOffset = FVector(0.f, FMath::FRandRange(-Amp, Amp), FMath::FRandRange(-Amp, Amp));
	}
	else
	{
		CameraBoom->SocketOffset = FVector::ZeroVector;
	}
	if (bAutoTest)
	{
		AutoDrive(DeltaSeconds);
	}
}

void ANyabloHero::Shake(float Strength, float Seconds)
{
	ShakeStrength = FMath::Max(ShakeStrength * (ShakeLeft > 0.f ? 1.f : 0.f), Strength);
	ShakeLeft = ShakeTotal = Seconds;
}

void ANyabloHero::OnDealtHit(int32 Targets)
{
	const float Heavy = FMath::Max(CurrentDamageScale, 1.f);   // combo finisher shakes harder
	Shake(bSkillSwing ? 22.f : (9.f + 3.f * Targets) * Heavy, bSkillSwing ? 0.35f : 0.15f * Heavy);
	// FOV punch (4-28): a quick zoom-in on contact that eases back out
	FovKickAmount = bSkillSwing ? FovKickDegrees * 2.f : FovKickDegrees * Heavy;
	FovKickLeft = FovKickSeconds;
}

void ANyabloHero::OnTookHit(float Amount)
{
	Shake(14.f, 0.2f);
}

void ANyabloHero::UseSkill()
{
	if (IsBusy() || IsDead() || SkillCooldownLeft > 0.f)
	{
		return;
	}
	ApplyClip(SkillClipIndex);
	CurrentDamageScale = 1.f;
	AttackPower = 1.f;
	if (StartAttack())
	{
		ComboIndex = 0;
		CapeGustLeft = CapeGustSeconds * 1.4f;
		bSkillSwing = true;
		SkillCooldownLeft = SkillCooldown;
		bMoveHeldAtSwingStart = !LastMoveInput.IsNearlyZero();
	}
}

void ANyabloHero::OnAttackHit()
{
	if (!bSkillSwing)
	{
		Super::OnAttackHit();
		return;
	}
	// Shockwave: ground slam around the hero
	bHitApplied = true;
	HitActionTime = ActionTime;
	bSkillSwing = false;
	AttackPower = SkillKnockbackPower;   // victims fly further out of the ring
	const FVector Feet = GetActorLocation() - FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight() - 10.f);
	SpawnVFX(SkillVFX, Feet, FRotator::ZeroRotator, SkillVFXScale);
	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(NyabloShockwave), false, this);
	GetWorld()->OverlapMultiByObjectType(Overlaps, GetActorLocation(), FQuat::Identity, FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(SkillRadius), Params);
	TSet<AActor*> Damaged;
	for (const FOverlapResult& Overlap : Overlaps)
	{
		ANyabloCharacter* Target = Cast<ANyabloCharacter>(Overlap.GetActor());
		if (Target && !Damaged.Contains(Target) && IsHostileTo(Target) && !Target->IsDead())
		{
			Damaged.Add(Target);
			UGameplayStatics::ApplyDamage(Target, SkillDamage, GetController(), this, UDamageType::StaticClass());
		}
	}
	AttackPower = 1.f;
	if (bAttackerHitStop)
	{
		StartHitStop(HitStopSeconds * 1.5f);
	}
	bSkillSwing = true;   // OnDealtHit reads it for the bigger shake
	OnDealtHit(Damaged.Num());
	bSkillSwing = false;
	UE_LOG(LogNyabloHero, Log, TEXT("NYABLO_SKILL shockwave hits=%d"), Damaged.Num());
}

void ANyabloHero::MeasureHipJump()
{
	// Teleport check: the drawn body (Hip, world) must not jump between frames. Measured at the start of Tick = the
	// frame just drawn. World, not relative to the capsule: the swing-end lunge moves the capsule under a body that
	// stays put (4-27). Running at 650 cm/s moves the hip ~11 cm per 60 fps frame.
	const FVector Hip = GetMesh()->GetSocketLocation(TEXT("Hip"));
	if (AutoTime > 0.5f && !IsDead())
	{
		const float Jump = FVector::Dist2D(Hip, LastHipOffset);
		MaxHipJump = FMath::Max(MaxHipJump, Jump);
		if (Jump > 40.f)
		{
			const FVector LocalHip = GetActorTransform().InverseTransformPosition(Hip);
			UE_LOG(LogNyabloHero, Log, TEXT("NYABLO_JUMP t=%.2f jump=%.0fcm action=%d anim=%s pos=%.2f yaw=%.0f localHip=(%.0f,%.0f,%.0f) speed=%.0f"),
				AutoTime, Jump, (int32)Action, CurrentLoop ? *CurrentLoop->GetName() : TEXT("attack/none"),
				AnimPosition(), GetActorRotation().Yaw, LocalHip.X, LocalHip.Y, LocalHip.Z, GetVelocity().Size2D());
		}
	}
	LastHipOffset = Hip;   // (name kept: now the last drawn hip position, world)

	// pose jump (4-28): mean hip-relative joint travel since the last drawn frame, % of body height, split into frames
	// where a clip change was drawn and all others. Before the crossfade, clip changes jumped 14-35 %.
	// body only: the sword arm legitimately moves 10-25 % of height per frame in the snap, which hid the pops
	static const FName Joints[] = { TEXT("Head"), TEXT("Spine02"), TEXT("L_Clavicle"), TEXT("R_Clavicle"),
		TEXT("R_Foot"), TEXT("L_Foot"), TEXT("R_Calf"), TEXT("L_Calf") };
	const UNyabloAnimInstance* Blend = GetBlendAnim();
	TArray<FVector> Rel;
	for (const FName& J : Joints)
	{
		Rel.Add(GetActorQuat().UnrotateVector(GetMesh()->GetSocketLocation(J) - Hip));
	}
	const int32 Plays = Blend ? Blend->GetPlayCount() : 0;
	if (LastJointRel.Num() == Rel.Num() && AutoTime > 0.5f && !IsDead())
	{
		float Sum = 0.f;
		for (int32 i = 0; i < Rel.Num(); ++i)
		{
			Sum += FVector::Dist(Rel[i], LastJointRel[i]);
		}
		const float Pct = Sum / Rel.Num() / FMath::Max(GetBodyHeight(), 1.f) * 100.f;
		float& Max = Plays != LastPlayCount ? MaxSwitchJump : MaxSteadyJump;
		Max = FMath::Max(Max, Pct);
		if (Pct > 6.f)
		{
			UE_LOG(LogNyabloHero, Log, TEXT("NYABLO_POSEJUMP t=%.2f jump=%.1f%% switch=%d anim=%s pos=%.2f rate=%.2f blendLeft=%.3f action=%d"),
				AutoTime, Pct, Plays != LastPlayCount ? 1 : 0, Blend && Blend->GetCurrentAnim() ? *Blend->GetCurrentAnim()->GetName() : TEXT("-"),
				AnimPosition(), AnimRate(), Blend ? Blend->BlendLeft : 0.f, (int32)Action);
		}
	}
	LastJointRel = Rel;
	LastPlayCount = Plays;
}

void ANyabloHero::AutoDrive(float DeltaSeconds)
{
	AutoTime += DeltaSeconds;
	// -NyabloBurst: 12 frames 0.1 s apart while fighting (cloth / motion check) instead of the 5 overview shots
	// -NyabloBurstStart=0.6: start the burst there instead of 4.0 s; -NyabloBurstStep=0.0333 -NyabloBurstCount=40: finer
	// frames for swing timing (4-28; pair with -UseFixedTimeStep -FPS=30 so slow screenshot frames don't skip game time)
	static TArray<float> ShotTimes;
	if (ShotTimes.Num() == 0)
	{
		if (FParse::Param(FCommandLine::Get(), TEXT("NyabloBurst")))
		{
			float Start = 4.f, Step = 0.1f;
			int32 Count = 12;
			FParse::Value(FCommandLine::Get(), TEXT("NyabloBurstStart="), Start);
			FParse::Value(FCommandLine::Get(), TEXT("NyabloBurstStep="), Step);
			FParse::Value(FCommandLine::Get(), TEXT("NyabloBurstCount="), Count);
			for (int32 i = 0; i < Count; ++i)
			{
				ShotTimes.Add(Start + Step * i);
			}
		}
		else
		{
			ShotTimes = { 3.f, 7.f, 11.f, 15.f, 19.f };
		}
	}
	const int32 NumShots = ShotTimes.Num();
	if (AutoShot < NumShots && AutoTime >= ShotTimes[AutoShot])
	{
		int32 Alive = 0;
		for (TActorIterator<ANyabloCharacter> It(GetWorld()); It; ++It)
		{
			Alive += (IsHostileTo(*It) && !It->IsDead()) ? 1 : 0;
		}
		const FString Name = FString::Printf(TEXT("nyablo_auto_%d.png"), AutoShot);
		FScreenshotRequest::RequestScreenshot(Name, true, false);
		UE_LOG(LogNyabloHero, Log, TEXT("NYABLO_AUTO shot=%s t=%.1f heroHP=%.0f enemiesAlive=%d maxHipJumpPerFrame=%.1fcm poseJumpSwitch=%.1f%% poseJumpSteady=%.1f%%"),
			*Name, AutoTime, Health, Alive, MaxHipJump, MaxSwitchJump, MaxSteadyJump);
		++AutoShot;
	}
	if (AutoTime > 21.f)
	{
		UKismetSystemLibrary::QuitGame(this, Cast<APlayerController>(GetController()), EQuitPreference::Quit, false);
		return;
	}
	if (AutoTime < 2.f || IsDead())
	{
		return;
	}

	ANyabloCharacter* Nearest = nullptr;
	float Best = TNumericLimits<float>::Max();
	for (TActorIterator<ANyabloCharacter> It(GetWorld()); It; ++It)
	{
		if (IsHostileTo(*It) && !It->IsDead())
		{
			const float D = FVector::Dist2D(It->GetActorLocation(), GetActorLocation());
			if (D < Best)
			{
				Best = D;
				Nearest = *It;
			}
		}
	}
	if (!Nearest || IsBusy())
	{
		return;
	}
	if (AutoCancelMoveLeft > 0.f)
	{
		AutoCancelMoveLeft -= DeltaSeconds;
		AddMovementInput(GetActorRightVector(), 1.f);
		return;
	}
	int32 Close = 0;
	for (TActorIterator<ANyabloCharacter> It(GetWorld()); It; ++It)
	{
		Close += (IsHostileTo(*It) && !It->IsDead() && FVector::Dist2D(It->GetActorLocation(), GetActorLocation()) < SkillRadius) ? 1 : 0;
	}
	if (Close >= 2 && SkillCooldownLeft <= 0.f)
	{
		UseSkill();
		return;
	}
	const float Reach = AttackReach + Nearest->GetCapsuleComponent()->GetScaledCapsuleRadius() + 40.f;
	if (Best > Reach)
	{
		AddMovementInput((Nearest->GetActorLocation() - GetActorLocation()).GetSafeNormal2D(), 1.f);
	}
	else
	{
		FaceLocation(Nearest->GetActorLocation());
		StartComboAttack();
	}
}
